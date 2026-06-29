//
//  DepthVideoWriter.swift
//  iPhUMI
//
//  Created by Austin Patel on 12/20/24.
//  Copyright © 2024 Apple. All rights reserved.
//

import AVFoundation
import Accelerate
import Foundation
import CoreVideo

class DepthVideoWriter {
    private let fileHandle: FileHandle
    private let width: Int
    private let height: Int
    private let halfData: UnsafeMutablePointer<UInt16>
    private let halfByteCount: Int

    init(outputURL: URL, width: Int, height: Int) throws {
        self.width = width
        self.height = height
        self.halfByteCount = width * height * MemoryLayout<UInt16>.size
        self.halfData = UnsafeMutablePointer<UInt16>.allocate(capacity: width * height)

        // Ensure file is created empty
        FileManager.default.createFile(atPath: outputURL.path, contents: nil, attributes: nil)
        self.fileHandle = try FileHandle(forWritingTo: outputURL)
    }

    deinit {
        halfData.deallocate()
        try? fileHandle.close()
    }

    func append(pixelBuffer: CVPixelBuffer) {
        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        guard let floatBaseAddress = CVPixelBufferGetBaseAddress(pixelBuffer) else {
            print("Failed to get base address of pixel buffer")
            CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly)
            return
        }

        var srcBuffer = vImage_Buffer(
            data: floatBaseAddress,
            height: vImagePixelCount(height),
            width: vImagePixelCount(width),
            rowBytes: width * MemoryLayout<Float>.size
        )

        var dstBuffer = vImage_Buffer(
            data: halfData,
            height: vImagePixelCount(height),
            width: vImagePixelCount(width),
            rowBytes: width * MemoryLayout<UInt16>.size
        )

        let error = vImageConvert_PlanarFtoPlanar16F(&srcBuffer, &dstBuffer, 0)
        if error != kvImageNoError {
            print("Error converting to Float16: \(error)")
            CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly)
            return
        }

        fileHandle.write(Data(bytesNoCopy: halfData, count: halfByteCount, deallocator: .none))

        CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly)
    }

    func finishWriting() {
        try? fileHandle.close()
    }
}
