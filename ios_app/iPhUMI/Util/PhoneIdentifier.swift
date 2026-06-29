//
//  PhoneIdentifier.swift
//  iPhUMI
//
//  Created by Austin Patel on 3/17/26.
//  Copyright © 2026 Apple. All rights reserved.
//

// mapping from: https://github.com/souzainf3/RNDeviceName/tree/master

import UIKit

public extension UIDevice {
    
    /// Returns the raw hardware identifier (e.g., "iPhone16,1")
    /// If running on a simulator, it returns the identifier of the device being simulated.
    var identifierName: String {
        // Check if we are running on a simulator to get the simulated device ID
        if let simModelIdentifier = ProcessInfo.processInfo.environment["SIMULATOR_MODEL_IDENTIFIER"] {
            return simModelIdentifier
        }
        
        var systemInfo = utsname()
        uname(&systemInfo)
        let machineMirror = Mirror(reflecting: systemInfo.machine)
        return machineMirror.children.reduce("") { identifier, element in
            guard let value = element.value as? Int8, value != 0 else { return identifier }
            return identifier + String(UnicodeScalar(UInt8(value)))
        }
    }

    /// Returns the human-readable name (e.g., "iPhone 15 Pro")
    /// Returns an empty string if no match is found.
    var commonName: String {
        let identifier = self.identifierName
        
        let deviceMapping: [(name: String, identifiers: [String])] = [
            ("iPhone 6S", ["iPhone8,1"]),
            ("iPhone 6S Plus", ["iPhone8,2"]),
            ("iPhone SE", ["iPhone8,4"]),
            ("iPhone 7", ["iPhone9,1", "iPhone9,3"]),
            ("iPhone 7 Plus", ["iPhone9,2", "iPhone9,4"]),
            ("iPhone 8", ["iPhone10,1", "iPhone10,4"]),
            ("iPhone 8 Plus", ["iPhone10,2", "iPhone10,5"]),
            ("iPhone X", ["iPhone10,3", "iPhone10,6"]),
            ("iPhone XS", ["iPhone11,2"]),
            ("iPhone XS Max", ["iPhone11,4", "iPhone11,6"]),
            ("iPhone XR", ["iPhone11,8"]),
            ("iPhone 11", ["iPhone12,1"]),
            ("iPhone 11 Pro", ["iPhone12,3"]),
            ("iPhone 11 Pro Max", ["iPhone12,5"]),
            ("iPhone SE (2nd gen)", ["iPhone12,8"]),
            ("iPhone 12 Mini", ["iPhone13,1"]),
            ("iPhone 12", ["iPhone13,2"]),
            ("iPhone 12 Pro", ["iPhone13,3"]),
            ("iPhone 12 Pro Max", ["iPhone13,4"]),
            ("iPhone 13 Mini", ["iPhone14,4"]),
            ("iPhone 13", ["iPhone14,5"]),
            ("iPhone 13 Pro", ["iPhone14,2"]),
            ("iPhone 13 Pro Max", ["iPhone14,3"]),
            ("iPhone SE (3rd gen)", ["iPhone14,6"]),
            ("iPhone 14", ["iPhone14,7"]),
            ("iPhone 14 Plus", ["iPhone14,8"]),
            ("iPhone 14 Pro", ["iPhone15,2"]),
            ("iPhone 14 Pro Max", ["iPhone15,3"]),
            ("iPhone 15", ["iPhone15,4"]),
            ("iPhone 15 Plus", ["iPhone15,5"]),
            ("iPhone 15 Pro", ["iPhone16,1"]),
            ("iPhone 15 Pro Max", ["iPhone16,2"]),
            ("iPhone 16 Pro", ["iPhone17,1"]),
            ("iPhone 16 Pro Max", ["iPhone17,2"]),
            ("iPhone 16", ["iPhone17,3"]),
            ("iPhone 16 Plus", ["iPhone17,4"]),
            ("iPhone 16e", ["iPhone17,5"]),
            ("iPhone 17 Pro", ["iPhone18,1"]),
            ("iPhone 17 Pro Max", ["iPhone18,2"]),
            ("iPhone 17", ["iPhone18,3"]),
            ("iPhone Air", ["iPhone18,4"])
        ]

        return deviceMapping.first(where: { $0.identifiers.contains(identifier) })?.name ?? ""
    }
}
