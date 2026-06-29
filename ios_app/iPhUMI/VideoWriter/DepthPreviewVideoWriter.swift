//
//  DepthPreviewVideoWriter.swift
//  iPhUMI
//
//  Created by Austin Patel on 12/20/24.
//  Copyright © 2024 Apple. All rights reserved.
//

import AVFoundation
import Accelerate

class DepthPreviewVideoWriter {
    private var assetWriter: AVAssetWriter!
    private var assetWriterInput: AVAssetWriterInput!
    private var pixelBufferAdaptor: AVAssetWriterInputPixelBufferAdaptor!
    private var isWritingStarted = false

    init(outputURL: URL, width: Int, height: Int) throws {
        // Initialize AVAssetWriter
        assetWriter = try AVAssetWriter(outputURL: outputURL, fileType: .mov)

        // Define video settings
        let outputSettings: [String: Any] = [
            AVVideoCodecKey: AVVideoCodecType.h264,
            AVVideoWidthKey: width,
            AVVideoHeightKey: height
        ]

        // Create AVAssetWriterInput
        assetWriterInput = AVAssetWriterInput(mediaType: .video, outputSettings: outputSettings)
        assetWriterInput.expectsMediaDataInRealTime = true
        assetWriter.add(assetWriterInput)

        // Create Pixel Buffer Adaptor
        pixelBufferAdaptor = AVAssetWriterInputPixelBufferAdaptor(
            assetWriterInput: assetWriterInput,
            sourcePixelBufferAttributes: [
                kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_OneComponent32Float,
                kCVPixelBufferWidthKey as String: width,
                kCVPixelBufferHeightKey as String: height
            ]
        )
    }

    func startWriting(at time: CMTime) {
        assetWriter.startWriting()
        assetWriter.startSession(atSourceTime: time)
        isWritingStarted = true
    }

    func append(pixelBuffer: CVPixelBuffer, at time: CMTime) {
        guard isWritingStarted, assetWriterInput.isReadyForMoreMediaData else { return }

        // Convert the depth map to a format that AVAssetWriter supports
        if let convertedBuffer = Self.convertDepthBufferToOneComponent32Float(pixelBuffer: pixelBuffer) {
            pixelBufferAdaptor.append(convertedBuffer, withPresentationTime: time)
        }
    }

    func finishWriting(completion: @escaping () -> Void) {
        assetWriterInput.markAsFinished()
        assetWriter.finishWriting {
            completion()
        }
    }

    // Converts the kCVPixelFormatType_DepthFloat32 to kCVPixelFormatType_OneComponent32Float.
    public static func convertDepthBufferToOneComponent32Float(
        pixelBuffer: CVPixelBuffer,
        maxDistanceMeters: Float = 1.0
    ) -> CVPixelBuffer? {
        let width = CVPixelBufferGetWidth(pixelBuffer)
        let height = CVPixelBufferGetHeight(pixelBuffer)
        let totalPixels = width * height

        // Create a new pixel buffer with the desired format
        var convertedBuffer: CVPixelBuffer?
        let attributes: [String: Any] = [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_OneComponent32Float,
            kCVPixelBufferWidthKey as String: width,
            kCVPixelBufferHeightKey as String: height
        ]
        CVPixelBufferCreate(nil, width, height, kCVPixelFormatType_OneComponent32Float, attributes as CFDictionary, &convertedBuffer)

        guard let outputBuffer = convertedBuffer else {
            print("Failed to create converted pixel buffer")
            return nil
        }

        // Lock the base address of the pixel buffers for reading and writing
        CVPixelBufferLockBaseAddress(pixelBuffer, .readOnly)
        CVPixelBufferLockBaseAddress(outputBuffer, [])

        defer {
            CVPixelBufferUnlockBaseAddress(pixelBuffer, .readOnly)
            CVPixelBufferUnlockBaseAddress(outputBuffer, [])
        }

        // Get the pointers to the base addresses of the input and output buffers
        if let inputBaseAddress = CVPixelBufferGetBaseAddress(pixelBuffer),
           let outputBaseAddress = CVPixelBufferGetBaseAddress(outputBuffer) {

            let inputPointer = inputBaseAddress.bindMemory(to: Float.self, capacity: totalPixels)
            let outputPointer = outputBaseAddress.bindMemory(to: Float.self, capacity: totalPixels)

            // Use Accelerate framework to scale all elements by 1 / maxDistance.
            var scaleFactor: Float = 1 / maxDistanceMeters
            vDSP_vsmul(inputPointer, 1, &scaleFactor, outputPointer, 1, vDSP_Length(totalPixels))
        }

        return outputBuffer
    }
    
}
