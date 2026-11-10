#pragma once

#import <Cocoa/Cocoa.h>

// The real dispatcher is compiled, but cannot resolve printer APIs.
@interface SyntheticPrinter : NSObject
+ (instancetype)printerWithName:(NSString *)name;
- (NSArray *)stringListForKey:(NSString *)key inTable:(NSString *)table;
- (NSString *)stringForKey:(NSString *)key inTable:(NSString *)table;
@end

@interface SyntheticPrintInfo : NSObject
+ (SyntheticPrinter *)defaultPrinter;
@end

#define NSPrinter SyntheticPrinter
#define NSPrintInfo SyntheticPrintInfo
