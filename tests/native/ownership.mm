#include "4DPluginAPI.h"
#include "PrivateTypes.h"
#include "EntryPoints.h"

#include <cassert>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <stdexcept>

static int failures;
static bool nullEmpty;
static bool failHandle;
static bool failCommand;
static unsigned printerCalls;
static CUTF16String expectedPath;
static CUTF16String expectedFormat;
static std::map<PA_Unichar *, size_t> strings;
static std::map<PA_Handle, size_t> handles;
struct SyntheticPicture { unsigned refs; std::vector<uint8_t> bytes; };
static std::map<PA_Picture, SyntheticPicture *> pictures;

static void check(bool condition, const char *name)
{
    if (!condition) {
        std::cerr << "FAIL: " << name << '\n';
        ++failures;
    }
}

static CUTF16String text(const char *utf8)
{
    CFStringRef s = CFStringCreateWithBytes(kCFAllocatorDefault,
        reinterpret_cast<const UInt8 *>(utf8), std::strlen(utf8),
        kCFStringEncodingUTF8, false);
    assert(s);
    CUTF16String result(CFStringGetLength(s), 0);
    if (!result.empty())
        CFStringGetCharacters(s, CFRangeMake(0, result.size()), &result[0]);
    CFRelease(s);
    return result;
}

static PA_Unistring makeString(const PA_Unichar *source)
{
    size_t units = 0;
    if (source)
        while (source[units]) ++units;
    PA_Unistring result = {};
    if (units || !nullEmpty) {
        result.fString = static_cast<PA_Unichar *>(std::malloc((units + 1) * sizeof(PA_Unichar)));
        assert(result.fString);
        if (units) std::memcpy(result.fString, source, units * sizeof(PA_Unichar));
        result.fString[units] = 0;
        result.fLength = static_cast<PA_long32>(units);
        PA_Unichar *buffer = result.fString;
        strings[buffer] = units;
    }
    return result;
}

static void releaseString(PA_Unistring value)
{
    if (!value.fString) {
        check(value.fLength == 0, "null string length");
        return;
    }
    PA_Unichar *buffer = value.fString;
    auto it = strings.find(buffer);
    if (it == strings.end()) {
        check(false, "path string double-disposal / invalid string owner");
        return;
    }
    check(it->second == static_cast<size_t>(value.fLength), "string length and allocation");
    check(value.fString[value.fLength] == 0, "string terminator");
    std::free(value.fString);
    strings.erase(it);
}

static void expectString(PA_Unistring value, const CUTF16String &expected)
{
    check(value.fLength == static_cast<PA_long32>(expected.size()), "exact UTF16 code-unit count");
    if (!value.fString) {
        check(expected.empty(), "null only represents empty");
        return;
    }
    PA_Unichar *buffer = value.fString;
    check(strings.count(buffer) != 0, "text remains live");
    check(CUTF16String(value.fString, value.fLength) == expected, "exact text contents");
    check(value.fString[value.fLength] == 0, "text terminator boundary");
}

static PA_Picture makePicture(const void *bytes, size_t len)
{
    auto *p = new SyntheticPicture{1, {}};
    if (len) {
        assert(bytes);
        const auto *first = static_cast<const uint8_t *>(bytes);
        p->bytes.assign(first, first + len);
    }
    pictures[p] = p;
    return p;
}

static void releasePicture(PA_Picture p)
{
    if (!p) return;
    auto it = pictures.find(p);
    assert(it != pictures.end());
    if (--it->second->refs == 0) {
        delete it->second;
        pictures.erase(it);
    }
}

static void clear(PA_Variable *v)
{
    switch (v->fType) {
        case eVK_Undefined: case eVK_Longint: case eVK_Real: break;
        case eVK_Unistring: releaseString(v->uValue.fString); break;
        case eVK_Picture: releasePicture(v->uValue.fPicture); break;
        case eVK_ArrayUnicode:
            if (v->uValue.fArray.fData) {
                auto *elements = reinterpret_cast<PA_Unistring *>(*v->uValue.fArray.fData);
                for (PA_long32 i = 0; i <= v->uValue.fArray.fNbElements; ++i)
                    releaseString(elements[i]);
                PA_DisposeHandle(v->uValue.fArray.fData);
            }
            break;
        case eVK_ArrayReal: PA_DisposeHandle(v->uValue.fArray.fData); break;
        default: throw std::runtime_error("unmodelled variable cleanup (including raw-kind0 sentinel)");
    }
    *v = {};
    v->fType = eVK_Undefined;
}

static void engine(short selector, EngineBlock *eb)
{
    switch (selector) {
        case EX_CREATE_UNISTRING:
            eb->fUniString1 = makeString(reinterpret_cast<PA_Unichar *>(eb->fHandle));
            break;
        case EX_SET_UNISTRING: {
            PA_Unistring copy = makeString(reinterpret_cast<PA_Unichar *>(eb->fHandle));
            releaseString(eb->fUniString1);
            eb->fUniString1 = copy;
            break;
        }
        case EX_DISPOSE_UNISTRING: releaseString(eb->fUniString1); break;
        case EX_CREATE_PICTURE:
            eb->fPicture = makePicture(eb->fPtr1, eb->fParam1);
            eb->fError = 0;
            break;
        case EX_DUPLICATE_PICTURE:
            if (eb->fPicture) {
                PA_Picture value = eb->fPicture;
                auto *p = pictures.at(value);
                if (eb->fParam1 == 0) ++p->refs;
                else eb->fPicture = makePicture(p->bytes.data(), p->bytes.size());
            }
            break;
        case EX_DISPOSE_PICTURE: releasePicture(eb->fPicture); break;
        case EX_GET_PICTURE_DATA:
            // Metadata string ownership is deliberately not inferred.
            eb->fUniString1 = {};
            eb->fError = eER_IncompatibleTypes;
            break;
        case EX_CLEAR_VARIABLE: clear(static_cast<PA_Variable *>(eb->fPtr1)); break;
        case EX_HANDLE_MANAGER: {
            PA_Handle h = eb->fHandle;
            eb->fError = 0;
            switch (eb->fParam1) {
                case 1:
                    if (failHandle) {
                        failHandle = false;
                        eb->fHandle = nullptr;
                        eb->fError = eER_IncompatibleTypes;
                        break;
                    }
                    h = static_cast<PA_Handle>(std::malloc(sizeof(char *)));
                    assert(h);
                    *h = static_cast<char *>(std::calloc(1, std::max<sLONG_PTR>(1, static_cast<sLONG_PTR>(eb->fParam2))));
                    assert(*h);
                    handles[h] = eb->fParam2;
                    eb->fHandle = h;
                    break;
                case 2:
                    assert(handles.erase(h) == 1);
                    std::free(*h);
                    std::free(h);
                    break;
                case 3: {
                    size_t old = handles.at(h);
                    *h = static_cast<char *>(std::realloc(*h, std::max<sLONG_PTR>(1, static_cast<sLONG_PTR>(eb->fParam2))));
                    assert(*h);
                    if (static_cast<size_t>(eb->fParam2) > old)
                        std::memset(*h + old, 0xA5, eb->fParam2 - old);
                    handles[h] = eb->fParam2;
                    break;
                }
                case 4: eb->fParam2 = handles.at(h); break;
                case 5: eb->fParam3 = reinterpret_cast<sLONG_PTR>(h ? *h : nullptr); break;
                case 6: break;
                default: throw std::runtime_error("unmodelled handle operation");
            }
            break;
        }
        case EX_CONVERT_CHARSET_TO_CHARSET: {
            check(eb->fParam2 == eVTC_UTF_8 && eb->fParam4 == eVTC_UTF_16,
                  "charset direction");
            check(eb->fParam3 >= 2 && eb->fParam3 % sizeof(PA_Unichar) == 0,
                  "UTF16 capacity is bytes");
            check(eb->fParam3 == eb->fParam1 * static_cast<sLONG_PTR>(sizeof(PA_Unichar)) +
                  static_cast<sLONG_PTR>(sizeof(PA_Unichar)), "exact format buffer capacity");
            CFStringRef s = CFStringCreateWithBytes(kCFAllocatorDefault,
                static_cast<const UInt8 *>(eb->fPtr1), eb->fParam1, kCFStringEncodingUTF8, false);
            assert(s);
            CFIndex used = 0;
            CFIndex units = CFStringGetBytes(s, CFRangeMake(0, CFStringGetLength(s)),
                kCFStringEncodingUTF16LE, 0, false, static_cast<UInt8 *>(eb->fPtr2),
                eb->fParam3, &used);
            check(units == CFStringGetLength(s), "complete charset conversion");
            check(used == units * static_cast<CFIndex>(sizeof(PA_Unichar)),
                  "conversion returns bytes excluding terminator");
            check(used + static_cast<CFIndex>(sizeof(PA_Unichar)) <= eb->fParam3,
                  "format conversion leaves room for terminator");
            check(static_cast<PA_Unichar *>(eb->fPtr2)[units] == 0,
                  "preinitialized format terminator remains intact");
            eb->fParam3 = used;
            eb->fError = 0;
            CFRelease(s);
            break;
        }
        case EX_EXECUTE_COMMAND_BY_ID: {
            auto **args = static_cast<PA_Variable **>(eb->fPtr1);
            auto *returned = static_cast<PA_Variable *>(eb->fPtr2);
            assert(returned->fType == eVK_Undefined);
            eb->fError = 0;
            if (failCommand) {
                failCommand = false;
                eb->fError = eER_IncompatibleTypes;
                break;
            }
            switch (eb->fParam1) {
                case 678:
                    expectString(args[0]->uValue.fString, expectedPath);
                    clear(args[1]);
                    PA_SetPictureVariable(args[1], makePicture("file", 4));
                    break;
                case 1002:
                    expectString(args[1]->uValue.fString, expectedFormat);
                    [[fallthrough]];
                case 988: {
                    assert(pictures.count(PA_GetPictureVariable(*args[0])));
                    clear(args[0]);
                    PA_SetPictureVariable(args[0], makePicture("converted", 9));
                    break;
                }
                case 457:
                    assert(pictures.count(PA_GetPictureVariable(*args[0])));
                    PA_SetLongintVariable(args[1], 640);
                    PA_SetLongintVariable(args[2], 480);
                    break;
                case 679:
                    assert(pictures.count(PA_GetPictureVariable(*args[0])));
                    check(PA_GetLongintVariable(*args[2]) == 16 &&
                          PA_GetLongintVariable(*args[3]) == 8, "thumbnail scalar inputs");
                    clear(args[1]);
                    PA_SetPictureVariable(args[1], makePicture("thumb", 5));
                    break;
                case 9000: {
                    PA_Unistring result = makeString(text("owned result").c_str());
                    PA_SetStringVariable(returned, &result);
                    break;
                }
                case 9001:
                    expectString(args[0]->uValue.fString, text("reject"));
                    break;
                default: throw std::runtime_error("unmodelled command");
            }
            break;
        }
        case EX_CALL_BY_PROCID: {
            auto *variables = reinterpret_cast<PA_Variable *>(*eb->fHandle);
            assert(variables[0].fType == eVK_Undefined);
            PA_Unistring result = makeString(text("method result").c_str());
            PA_SetStringVariable(&variables[0], &result);
            eb->fError = 0;
            break;
        }
        default: throw std::runtime_error("unmodelled engine entry point");
    }
}

@implementation SyntheticPrinter
+ (instancetype)printerWithName:(NSString *)name
{
    ++printerCalls;
    assert(name);
    return [[[self alloc] init] autorelease];
}
- (NSArray *)stringListForKey:(NSString *)key inTable:(NSString *)table
{
    assert([key isEqualToString:@"Resolution"] && [table isEqualToString:@"PPD"]);
    return @[@"600x1200dpi", @"300x300dpi"];
}
- (NSString *)stringForKey:(NSString *)key inTable:(NSString *)table
{
    if ([key isEqualToString:@"DefaultResolution"]) return @"600x1200dpi";
    if ([key isEqualToString:@"Resolution/600x1200dpi"]) return @"600x1200dpi";
    if ([key isEqualToString:@"Resolution/300x300dpi"]) return @"300x300dpi";
    throw std::runtime_error("unmodelled synthetic printer key");
}
@end
@implementation SyntheticPrintInfo
+ (SyntheticPrinter *)defaultPrinter
{
    throw std::runtime_error("default printer path must not be used");
}
@end

static const char *fixtures[] = {"ASCII", "\xE6\x97\xA5\xE6\x9C\xAC", "A\xF0\x9F\x98\x80Z", ""};

static void pathOwners()
{
    for (const char *fixture : fixtures) {
        expectedPath = text(fixture);
        CUTF8String path(reinterpret_cast<const uint8_t *>(fixture));
        CPicture p;
        p.fromFileAtPath(&path);
        check(pictures.at(p.getPicture())->bytes.size() == 4, "file output survives argument cleanup");
        failCommand = true;
        p.fromFileAtPath(&path);
        check(pictures.count(p.getPicture()) == 1, "failed command retains valid picture");
    }
}

static void temporaryOwner()
{
    for (unsigned i = 0; i != 20; ++i) {
        CPicture p;
        const uint8_t bytes[] = {1, 2, 3};
        p.setBytes(bytes, sizeof(bytes));
        check(pictures.at(p.getPicture())->bytes == std::vector<uint8_t>({1, 2, 3}),
              "setBytes exact synthetic payload");
        p.setBytes(nullptr, 0);
        check(pictures.at(p.getPicture())->bytes.empty(), "empty picture payload");
    }
}

static void copyUnits()
{
    for (const char *format : {".png", "\xE6\x97\xA5", "\xF0\x9F\x98\x80", ""}) {
        CPicture p;
        expectedFormat = text(format);
        PA_Picture result = p.createCopy(format);
        check(pictures.at(result)->bytes.size() == 9, "copy owning output survives local cleanup");
        PA_DisposePicture(result);
    }
}

static void commandOwners()
{
    PA_Picture handoff = nullptr;
    {
        CPicture p;
        handoff = p.createGrayScale();
        unsigned width = 0, height = 0;
        p.getSize(&width, &height);
        check(width == 640 && height == 480, "synchronous borrowed input results");
        PA_Picture thumb = p.createThumbnail(16, 8);
        check(pictures.count(p.getPicture()) == 1, "borrowed picture input remains live");
        PA_DisposePicture(thumb);
        failHandle = true;
        PA_Picture unchanged = p.createGrayScale();
        check(unchanged == p.getPicture(), "failed command handoff keeps independent retain");
        PA_DisposePicture(unchanged);
    }
    check(pictures.at(handoff)->bytes.size() == 9, "owning handoff outlives wrapper");
    PA_DisposePicture(handoff);
}

static void arraysAndScalars()
{
    PA_Variable array = PA_CreateVariable(eVK_ArrayUnicode);
    BytePtr params[] = {reinterpret_cast<BytePtr>(&array)};
    ARRAY_TEXT output;
    for (const char *fixture : fixtures) {
        CUTF16String value = text(fixture);
        output.appendUTF16String(&value);
    }
    output.toParamAtIndex(params, 1);
    std::vector<PA_Unistring> churn;
    for (unsigned i = 0; i != 100; ++i)
        churn.push_back(PA_CreateUnistring(const_cast<PA_Unichar *>(text("allocator churn").c_str())));
    for (PA_Unistring &value : churn) PA_DisposeUnistring(&value);
    ARRAY_TEXT copied;
    copied.fromParamAtIndex(params, 1);
    for (unsigned i = 0; i != 4; ++i)
        expectString(PA_GetStringInArray(array, i), text(fixtures[i]));
    check(PA_GetStringInArray(array, 0).fString != PA_GetStringInArray(array, 1).fString,
          "independent text element allocations");
    output.toParamAtIndex(params, 1);
    output.setSize(1);
    output.toParamAtIndex(params, 1);
    PA_ClearVariable(&array);
    for (unsigned i = 0; i != 4; ++i) {
        CUTF16String value;
        copied.copyUTF16StringAtIndex(&value, i);
        check(value == text(fixtures[i]), "borrowed input copied before mutation and clear");
    }
    array = PA_CreateVariable(eVK_ArrayUnicode);
    PA_Unistring owned = PA_CreateUnistring(const_cast<PA_Unichar *>(text("reject").c_str()));
    PA_Variable wrong = PA_CreateVariable(eVK_Longint);
    PA_Variable noData = {};
    noData.fType = eVK_ArrayUnicode;
    for (PA_long32 i : {-1, 1}) PA_SetStringInArray(array, i, &owned);
    PA_SetStringInArray(wrong, 0, &owned);
    PA_SetStringInArray(noData, 0, &owned);
    PA_SetStringInArray(array, 0, nullptr);
    expectString(owned, text("reject"));
    PA_SetStringInArray(array, 0, &owned);
    expectString(PA_GetStringInArray(array, 0), text("reject"));
    C_TEXT callbackText;
    PA_Unistring borrowed = PA_GetStringInArray(array, 0);
    callbackText.setUTF16String(&borrowed);
    PA_ClearVariable(&array);
    PA_Unistring independent = PA_CreateUnistring(const_cast<PA_Unichar *>(callbackText.getUTF16StringPtr()));
    PA_Variable callback = PA_CreateVariable(eVK_Undefined);
    PA_SetStringVariable(&callback, &independent);
    PA_Variable callbackResult = PA_ExecuteCommandByID(9001, &callback, 1);
    PA_ClearVariable(&callbackResult);
    PA_ClearVariable(&callback);
    for (const char *fixture : fixtures) {
        CUTF16String value = text(fixture);
        PA_Unistring source = PA_CreateUnistring(const_cast<PA_Unichar *>(value.c_str()));
        BytePtr input[] = {reinterpret_cast<BytePtr>(&source)};
        C_TEXT wrapper;
        wrapper.fromParamAtIndex(input, 1);
        PA_DisposeUnistring(&source);
        source = PA_CreateUnistring(nullptr);
        wrapper.toParamAtIndex(input, 1);
        expectString(source, value);
        PA_DisposeUnistring(&source);
        source = PA_CreateUnistring(nullptr);
        PA_Unistring *destination = &source;
        wrapper.setReturn(reinterpret_cast<sLONG_PTR *>(&destination));
        expectString(source, value);
        PA_DisposeUnistring(&source);
        source = PA_CreateUnistring(nullptr);
        PluginBlock returned = {};
        returned.fResult = &destination;
        PA_ReturnString(&returned, const_cast<PA_Unichar *>(value.c_str()));
        expectString(source, value);
        PA_DisposeUnistring(&source);
    }
}

static void failureContracts()
{
    PA_Variable parameter = PA_CreateVariable(eVK_Longint);
    failHandle = true;
    PA_Variable result = PA_ExecuteCommandByID(9000, &parameter, 1);
    check(result.fType == 0, "command handle failure returns raw-kind0 sentinel");
    check(PA_GetVariableKind(result) == eVK_Unistring, "normalization is not sentinel ownership");
    failHandle = true;
    result = PA_ExecuteMethodByID(1, &parameter, 1);
    check(result.fType == eVK_Undefined, "method handle failure is Undefined");
    PA_ClearVariable(&result);
    result = PA_ExecuteCommandByID(9000, &parameter, 1);
    expectString(result.uValue.fString, text("owned result"));
    PA_ClearVariable(&result);
    result = PA_ExecuteMethodByID(1, &parameter, 1);
    expectString(result.uValue.fString, text("method result"));
    PA_ClearVariable(&result);
}

static void dispatcher()
{
    for (const char *fixture : fixtures) {
        PA_Unistring name = makeString(text(fixture).c_str());
        PA_Unistring port = makeString(text("").c_str());
        PA_Variable x = PA_CreateVariable(eVK_ArrayReal), y = PA_CreateVariable(eVK_ArrayReal);
        BytePtr args[] = {reinterpret_cast<BytePtr>(&name), reinterpret_cast<BytePtr>(&x),
            reinterpret_cast<BytePtr>(&y), reinterpret_cast<BytePtr>(&port)};
        sLONG_PTR result = 0;
        FourDPackex(1, args, nullptr, &result);
        check(PA_GetArrayNbElements(x) == 2 && PA_GetRealInArray(x, 1) == 600 &&
              PA_GetRealInArray(y, 1) == 1200 && PA_GetRealInArray(x, 2) == 300 &&
              PA_GetRealInArray(y, 2) == 300, "actual exported list dispatch exact results");
        PA_ClearVariable(&x);
        PA_ClearVariable(&y);
        double dx = 0, dy = 0;
        args[1] = reinterpret_cast<BytePtr>(&dx);
        args[2] = reinterpret_cast<BytePtr>(&dy);
        FourDPackex(2, args, nullptr, &result);
        check(dx == 600 && dy == 1200, "actual exported scalar dispatch exact results");
        expectString(name, text(fixture));
        releaseString(name);
        releaseString(port);
    }
    check(printerCalls == 8, "only synthetic printer dispatch was used");
}

int main(int argc, char **argv)
{
    assert(argc == 3);
    nullEmpty = std::string(argv[2]) == "null-empty";
    @autoreleasepool {
        PackInitBlock init = {};
        init.fCall4Dex = engine;
        FourDPackex(kInitPlugin, &init, nullptr, nullptr);
        const std::string name = argv[1];
        if (name == "path-owners") pathOwners();
        else if (name == "temporary-owner") temporaryOwner();
        else if (name == "copy-byte-units") copyUnits();
        else if (name == "command-empty-owners") commandOwners();
        else if (name == "array-scalar-contracts") arraysAndScalars();
        else if (name == "failure-sentinels") failureContracts();
        else if (name == "exported-dispatcher") dispatcher();
        else throw std::runtime_error("unknown case");
        check(strings.empty(), "all string owners released (including initial empties)");
        check(pictures.empty(), "all picture references released (including initial empties/output owners)");
        check(handles.empty(), "all handles released");
    }
    return failures ? 1 : 0;
}
