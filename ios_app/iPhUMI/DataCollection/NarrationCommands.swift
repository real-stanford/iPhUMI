//
//  NarrationCommands.swift
//  iPhUMI
//
//  Created by Austin Patel on 1/14/25.
//  Copyright © 2025 Apple. All rights reserved.
//

class NarrationCommands {

    static let startWords = ["start"]
    static let stopWords = ["stop"]
    static let doneWords = ["done"]
    static let deleteWords = ["delete"]

    public static func isStartWord(_ word: String) -> Bool {
        word.split(separator: " ").contains { startWords.contains($0.lowercased()) }
    }

    public static func isStopWord(_ word: String) -> Bool {
        word.split(separator: " ").contains { stopWords.contains($0.lowercased()) }
    }

    public static func isDoneWord(_ word: String) -> Bool {
        word.split(separator: " ").contains { doneWords.contains($0.lowercased()) }
    }

    public static func isDeleteWord(_ word: String) -> Bool {
        word.split(separator: " ").contains { deleteWords.contains($0.lowercased()) }
    }

}
