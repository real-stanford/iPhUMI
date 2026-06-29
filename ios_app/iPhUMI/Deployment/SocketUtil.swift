//
//  SocketUtil.swift
//  iPhUMI
//
//  Created by Austin Patel on 2/4/25.
//  Copyright © 2025 Apple. All rights reserved.
//

import CoreImage
import UIKit

class SocketUtil {
    static func encodePixelBufferToPNGBase64(_ ciImage: CIImage) -> String? {
        let context = CIContext()

        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent) else {
            return nil
        }
        
        let uiImage = UIImage(cgImage: cgImage)
        
        // Convert to PNG Data
        guard let pngData = uiImage.pngData() else { return nil }

        // Convert to Base64
        return pngData.base64EncodedString()
    }

    /// Encode CIImage to base64 JPEG. Use for Ethernet RGB to keep payload size small (avoids Socket.IO message limits at high resolution).
    static func encodeCIImageToJPEGBase64(_ ciImage: CIImage, compressionQuality: CGFloat = 0.9) -> String? {
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent) else {
            return nil
        }
        let uiImage = UIImage(cgImage: cgImage)
        guard let jpegData = uiImage.jpegData(compressionQuality: compressionQuality) else {
            return nil
        }
        return jpegData.base64EncodedString()
    }
    
    /// Encodes a depth CVPixelBuffer (32-bit float) to a Base64 string.
    static func encodeDepthPixelBufferToBase64(_ pixelBuffer: CVPixelBuffer) -> String? {
        let format = CVPixelBufferGetPixelFormatType(pixelBuffer)
        guard format == kCVPixelFormatType_DepthFloat32 else {
            print("Unsupported pixel format: \(format)")
            return nil
        }

        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly) }

        let width = CVPixelBufferGetWidth(pixelBuffer)
        let height = CVPixelBufferGetHeight(pixelBuffer)
        let bytesPerRow = CVPixelBufferGetBytesPerRow(pixelBuffer)

        guard let baseAddress = CVPixelBufferGetBaseAddress(pixelBuffer) else {
            print("Unable to get base address")
            return nil
        }

        let dataSize = bytesPerRow * height
        let data = Data(bytes: baseAddress, count: dataSize)

        return data.base64EncodedString()
    }
}
