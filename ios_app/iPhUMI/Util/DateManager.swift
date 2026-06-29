//
//  DateManager.swift
//  iPhUMI
//
//  Created by Austin Patel on 9/15/24.
//  Copyright © 2024 Apple. All rights reserved.
//

import Foundation

class DateManager {
    
    static func getISOFormatter() -> ISO8601DateFormatter {
        let dateFormatter = ISO8601DateFormatter()
        dateFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return dateFormatter
    }
    
}
