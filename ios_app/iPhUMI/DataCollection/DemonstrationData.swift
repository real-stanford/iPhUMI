//
//  DemonstrationData.swift
//  iPhUMI
//
//  Created by Austin Patel on 9/12/24.
//  Copyright © 2024 Apple. All rights reserved.
//

import Foundation
import simd
import CoreVideo
import CoreMedia
import Speech
import UIKit

extension simd_float4x4: Codable {
    public init(from decoder: Decoder) throws {
        var container = try decoder.unkeyedContainer()
        // Decode each row individually (instead of columns)
        let row0 = try container.decode(SIMD4<Float>.self)
        let row1 = try container.decode(SIMD4<Float>.self)
        let row2 = try container.decode(SIMD4<Float>.self)
        let row3 = try container.decode(SIMD4<Float>.self)
        // Convert rows into columns (row-major to column-major conversion)
        self.init(
            SIMD4<Float>(row0.x, row1.x, row2.x, row3.x),
            SIMD4<Float>(row0.y, row1.y, row2.y, row3.y),
            SIMD4<Float>(row0.z, row1.z, row2.z, row3.z),
            SIMD4<Float>(row0.w, row1.w, row2.w, row3.w)
        )
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.unkeyedContainer()
        // Convert columns into rows for row-major encoding
        let row0 = SIMD4<Float>(columns.0.x, columns.1.x, columns.2.x, columns.3.x)
        let row1 = SIMD4<Float>(columns.0.y, columns.1.y, columns.2.y, columns.3.y)
        let row2 = SIMD4<Float>(columns.0.z, columns.1.z, columns.2.z, columns.3.z)
        let row3 = SIMD4<Float>(columns.0.w, columns.1.w, columns.2.w, columns.3.w)
        // Encode each row individually
        try container.encode(row0)
        try container.encode(row1)
        try container.encode(row2)
        try container.encode(row3)
    }
}

extension simd_float3x3: Codable {
    public init(from decoder: Decoder) throws {
        var container = try decoder.unkeyedContainer()
        // Decode each row individually (row-major)
        let row0 = try container.decode(SIMD3<Float>.self)
        let row1 = try container.decode(SIMD3<Float>.self)
        let row2 = try container.decode(SIMD3<Float>.self)
        // Convert rows into columns (row-major to column-major conversion)
        self.init(
            SIMD3<Float>(row0.x, row1.x, row2.x),
            SIMD3<Float>(row0.y, row1.y, row2.y),
            SIMD3<Float>(row0.z, row1.z, row2.z)
        )
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.unkeyedContainer()
        // Convert columns into rows for row-major encoding
        let row0 = SIMD3<Float>(columns.0.x, columns.1.x, columns.2.x)
        let row1 = SIMD3<Float>(columns.0.y, columns.1.y, columns.2.y)
        let row2 = SIMD3<Float>(columns.0.z, columns.1.z, columns.2.z)
        // Encode each row individually
        try container.encode(row0)
        try container.encode(row1)
        try container.encode(row2)
    }
}

enum RecordingError: Error {
    case ultrawideNotYetInitialized
}

class TaskSegmentation {
    var taskStart: Date?
    var taskEnd: Date?
    var name: String?
    
    init() {
        
    }
    
    init(taskStart: Date, taskEnd: Date, name: String? = nil) {
        self.taskStart = taskStart
        self.taskEnd = taskEnd
        self.name = name
    }
}

enum DemonstrationType: String, Codable {
    case GripperCalibration = "gripper_calibration"
    case Demonstration = "demonstration"
}

enum DemonstrationLabelType: String, Codable {
    case Narration
    case Predefined
    case None
}

enum DemonstrationSaveType: String, Codable, CaseIterable {
    case JSON
    case RGB
    case UltrawideRGB
    case DepthMap
    case DepthPreviewMap
}

class DemonstrationData : Codable {
//    parameters we save in json
    var poseTimes: [String] = []
    var rgbTimes: [String] = []
    var ultrawideRGBTimes: [String] = []
    var depthTimes: [String] = []
    var depthFrameIsRepeat: [Bool] = []
    var poseTransforms: [simd_float4x4] = []
    var recordingStartTime: String
    var side: String = ""
    var type: DemonstrationType
    var gripperCalibrationRunName: String
    var sessionName: String
    var gripperID: String = "default"
    var hasRGB: Bool
    var hasUltrawideRGB: Bool
    var hasDepth: Bool
    var taskStartTimestamps: [String] = []
    var taskEndTimestamps: [String] = []
    var taskNames: [String] = []
    var narrationStartTimestamps: [String] = []
    var narrationEndTimestamps: [String] = []
    var narrationTexts: [String] = []
    var labelType: DemonstrationLabelType
    var hasAudio: Bool = false
    var isVoiceHost: Bool = false
    var sidesPresent: [String] = []
    var formatVersion: String = "v1"
    var deviceName: String
    var deviceIdentifier: String
    var mainCameraIntrinsics: simd_float3x3
    var ultrawideCameraIntrinsics: simd_float3x3
    var isErrorCorrection: Bool = false

//    parameters we do not save in json
    var recordingName: String
    var rgbVideoWriter: VideoWriter?
    var ultrawideRGBVideoWriter: VideoWriter?
    var depthVideoWriter: DepthVideoWriter?
    var depthPreviewVideoWriter: DepthPreviewVideoWriter?
    var lastDepthPixelBuffer: CVPixelBuffer? = nil
    var frameCount: Int = 0
    
    private enum CodingKeys : String, CodingKey {
//        these are the keys that are saved to .json
        case poseTimes
        case rgbTimes
        case ultrawideRGBTimes
        case depthTimes
        case depthFrameIsRepeat
        case poseTransforms
        case recordingStartTime
        case side
        case type
        case gripperCalibrationRunName
        case sessionName
        case gripperID
        case hasRGB
        case hasUltrawideRGB
        case hasDepth
        case frameCount
        case taskStartTimestamps
        case taskEndTimestamps
        case taskNames
        case narrationStartTimestamps
        case narrationEndTimestamps
        case narrationTexts
        case labelType
        case hasAudio
        case isVoiceHost
        case sidesPresent
        case formatVersion
        case deviceName
        case deviceIdentifier
        case mainCameraIntrinsics
        case ultrawideCameraIntrinsics
        case isErrorCorrection
    }
    
    required init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        poseTimes = try container.decode([String].self, forKey: .poseTimes)
        rgbTimes = try container.decode([String].self, forKey: .rgbTimes)
        ultrawideRGBTimes = try container.decode([String].self, forKey: .ultrawideRGBTimes)
        depthTimes = try container.decode([String].self, forKey: .depthTimes)
        depthFrameIsRepeat = (try? container.decode([Bool].self, forKey: .depthFrameIsRepeat)) ?? Array(repeating: false, count: depthTimes.count)
        poseTransforms = try container.decode([simd_float4x4].self, forKey: .poseTransforms)
        recordingStartTime = try container.decode(String.self, forKey: .recordingStartTime)
        side = try container.decode(String.self, forKey: .side)
        type = try container.decode(DemonstrationType.self, forKey: .type)
        gripperCalibrationRunName = try container.decode(String.self, forKey: .gripperCalibrationRunName)
        sessionName = try container.decode(String.self, forKey: .sessionName)
        gripperID = (try? container.decode(String.self, forKey: .gripperID)) ?? "default"
        hasRGB = try container.decode(Bool.self, forKey: .hasRGB)
        hasUltrawideRGB = try container.decode(Bool.self, forKey: .hasUltrawideRGB)
        hasDepth = try container.decode(Bool.self, forKey: .hasDepth)
        frameCount = try container.decode(Int.self, forKey: .frameCount)
        taskStartTimestamps = try container.decode([String].self, forKey: .taskStartTimestamps)
        taskEndTimestamps = try container.decode([String].self, forKey: .taskEndTimestamps)
        taskNames = try container.decode([String].self, forKey: .taskNames)
        narrationStartTimestamps = try container.decode([String].self, forKey: .narrationStartTimestamps)
        narrationEndTimestamps = try container.decode([String].self, forKey: .narrationEndTimestamps)
        narrationTexts = try container.decode([String].self, forKey: .narrationTexts)
        labelType = try container.decode(DemonstrationLabelType.self, forKey: .labelType)
        hasAudio = try container.decode(Bool.self, forKey: .hasAudio)
        isVoiceHost = (try? container.decode(Bool.self, forKey: .isVoiceHost)) ?? false
        sidesPresent = (try? container.decode([String].self, forKey: .sidesPresent)) ?? []
        formatVersion = try container.decode(String.self, forKey: .formatVersion)
        deviceName = try container.decode(String.self, forKey: .deviceName)
        deviceIdentifier = try container.decode(String.self, forKey: .deviceIdentifier)
        mainCameraIntrinsics = try container.decode(simd_float3x3.self, forKey: .mainCameraIntrinsics)
        ultrawideCameraIntrinsics = try container.decode(simd_float3x3.self, forKey: .ultrawideCameraIntrinsics)
        isErrorCorrection = (try? container.decode(Bool.self, forKey: .isErrorCorrection)) ?? false

        // recordingName is not stored in JSON, so set to empty string
        recordingName = ""
        
        // Initialize video writers as nil (they are not stored in JSON)
        rgbVideoWriter = nil
        ultrawideRGBVideoWriter = nil
        depthVideoWriter = nil
        depthPreviewVideoWriter = nil
    }
    
    init(recordingName: String, side: String, recordingStartTime: Date, demonstrationType: DemonstrationType, gripperCalibrationRunName: String, sessionName: String, gripperID: String, labelType: DemonstrationLabelType, isVoiceHost: Bool, sidesPresent: [String], mainCameraIntrinsics: simd_float3x3, ultrawideCameraIntrinsics: simd_float3x3) {
        self.side = side
        self.sidesPresent = sidesPresent
        self.recordingName = recordingName
        self.type = demonstrationType
        self.gripperCalibrationRunName = self.type == .Demonstration ? gripperCalibrationRunName : ""
        self.sessionName = sessionName
        self.gripperID = gripperID
        self.hasRGB = demonstrationType == .Demonstration
        self.hasUltrawideRGB = true
        self.hasDepth = demonstrationType == .Demonstration
        self.labelType = labelType
        self.isVoiceHost = isVoiceHost
        self.mainCameraIntrinsics = mainCameraIntrinsics
        self.ultrawideCameraIntrinsics = ultrawideCameraIntrinsics
        
        // start recording time
        self.recordingStartTime = "" // need to do this for next line to work
        self.recordingStartTime = DateManager.getISOFormatter().string(from: recordingStartTime)
        
        self.deviceName = UIDevice.current.commonName
        self.deviceIdentifier = UIDevice.current.identifierName
    }
    
    func logAudio(audioSampleBuffer: CMSampleBuffer) {
        if type == .Demonstration {
            ultrawideRGBVideoWriter?.appendAudio(sampleBuffer: audioSampleBuffer)
            rgbVideoWriter?.appendAudio(sampleBuffer: audioSampleBuffer)
            hasAudio = true
        }
    }
    
    func logFrame(pose: simd_float4x4, poseTime: Date, rgb: CVPixelBuffer, depthMap: CVPixelBuffer?, ultrawidergb: CVPixelBuffer?, arkitTimestamp: TimeInterval) {
        let poseTime = DateManager.getISOFormatter().string(from: poseTime)
        let arkitTimeString = String(format: "%.5f", arkitTimestamp)
        let frameTime = CMTimeMake(value: Int64(arkitTimestamp*10000), timescale: 10000) // trick to represent float as fraction
        
        // setup the RGB video writer if this is the first frame
        if self.hasRGB && rgbVideoWriter == nil {
            do {
                let rgbOutputUrl = try self.getURL(demonstrationSaveType: .RGB)
                self.rgbVideoWriter = try VideoWriter(outputURL: rgbOutputUrl, width: CVPixelBufferGetWidth(rgb), height: CVPixelBufferGetHeight(rgb), includeAudio: true)
                self.rgbVideoWriter!.startWriting(at: frameTime)
            } catch {
                print("Failed to open video writer for RGB")
            }
        }
        
        if self.hasUltrawideRGB && ultrawideRGBVideoWriter == nil, let ultrawidergb = ultrawidergb {
            do {
                let rgbOutputUrl = try self.getURL(demonstrationSaveType: .UltrawideRGB)
                self.ultrawideRGBVideoWriter = try VideoWriter(outputURL: rgbOutputUrl, width: CVPixelBufferGetWidth(ultrawidergb), height: CVPixelBufferGetHeight(ultrawidergb), includeAudio: true)
                self.ultrawideRGBVideoWriter!.startWriting(at: frameTime)
            } catch {
                print("Failed to open video writer for ultrawide RGB")
            }
        }
        
        if depthMap == nil && depthVideoWriter == nil {
            // nil on the first depth frame means the device has no LiDAR
            hasDepth = false
        }

        // setup the depth video writer if this is the first frame
        if self.hasDepth && depthVideoWriter == nil { // some devices don't have LiDAR so depthMap can be nil
            do {
                let depthOutputUrl = try self.getURL(demonstrationSaveType: .DepthMap)
                self.depthVideoWriter = try DepthVideoWriter(outputURL: depthOutputUrl, width: CVPixelBufferGetWidth(depthMap!), height: CVPixelBufferGetHeight(depthMap!))

                let depthPreviewOutputUrl = try self.getURL(demonstrationSaveType: .DepthPreviewMap)
                self.depthPreviewVideoWriter = try DepthPreviewVideoWriter(outputURL: depthPreviewOutputUrl, width: CVPixelBufferGetWidth(depthMap!), height: CVPixelBufferGetHeight(depthMap!))
                self.depthPreviewVideoWriter!.startWriting(at: frameTime)
            } catch {
                print("Failed to open video writer for depth")
            }
        }
        
        if self.hasRGB {
            // save the RGB image
//            print("Image dimensions: W: \(CVPixelBufferGetWidth(rgb)) H: \(CVPixelBufferGetHeight(rgb))")
            rgbVideoWriter!.appendVideo(pixelBuffer: rgb, at: frameTime)
            rgbTimes.append(poseTime)
        }
        
        if self.hasUltrawideRGB {
            if let ultrawidergb = ultrawidergb {
                ultrawideRGBVideoWriter!.appendVideo(pixelBuffer: ultrawidergb, at: frameTime)
                ultrawideRGBTimes.append(poseTime)
            } else {
                ultrawideRGBTimes.append("")
            }
        }
        
        if self.hasDepth, let depthVideoWriter = depthVideoWriter {
            let frameToWrite = depthMap ?? lastDepthPixelBuffer
            if let frameToWrite = frameToWrite {
                let isRepeat = depthMap == nil
                depthVideoWriter.append(pixelBuffer: frameToWrite)
                depthPreviewVideoWriter!.append(pixelBuffer: frameToWrite, at: frameTime)
                depthTimes.append(poseTime)
                depthFrameIsRepeat.append(isRepeat)
                if !isRepeat { lastDepthPixelBuffer = depthMap }
            }
        }
        
        // only need to save pose times and transforms if it's a demonstration
        if type == .Demonstration {
            poseTimes.append(poseTime)
            poseTransforms.append(pose)
        }
        self.frameCount += 1
    }
        
    private static func getLocalDemoDataFolderURL() throws -> URL {
        let folderURL = try FileManager.default.url(for: .documentDirectory,
                                                    in: .userDomainMask,
                                                    appropriateFor: nil,
                                                    create: false).appendingPathComponent("demonstration_data")
        
        if !FileManager.default.fileExists(atPath: folderURL.path) {
            try FileManager.default.createDirectory(at: folderURL, withIntermediateDirectories: true, attributes: nil)
        }
        
        return folderURL
    }
    
    /// Extracts the date directory from a recording name (format: YYYY-MM-DD)
    /// The recording name format is: YYYY-MM-DDTHH-MM-SS_...
    /// This extracts the date portion before the "T"
    public static func getDateDirectory(from recordingName: String) -> String {
        return recordingName.components(separatedBy: "T").first ?? "UnknownDate"
    }
    
    /// Constructs the folder URL for a specific demonstration without creating directories
    /// - Parameters:
    ///   - recordingName: The name of the recording/demonstration
    ///   - baseURL: The base directory URL where the date and demonstration folders should be created
    /// - Returns: The full URL to the demonstration folder
    private static func constructFolderURL(for recordingName: String, baseURL: URL) -> URL {
        let dateDir = getDateDirectory(from: recordingName)
        return baseURL
            .appendingPathComponent(dateDir)
            .appendingPathComponent(recordingName)
    }
    
    /// Gets the folder URL for a specific demonstration, creating the date and demonstration name subfolders if needed
    /// - Parameters:
    ///   - recordingName: The name of the recording/demonstration
    ///   - baseURL: The base directory URL where the date and demonstration folders should be created
    /// - Returns: The full URL to the demonstration folder
    public static func getFolderURL(for recordingName: String, baseURL: URL) throws -> URL {
        let folderURL = constructFolderURL(for: recordingName, baseURL: baseURL)
        
        if !FileManager.default.fileExists(atPath: folderURL.path) {
            try FileManager.default.createDirectory(at: folderURL, withIntermediateDirectories: true, attributes: nil)
        }
        
        return folderURL
    }
    
    /// Convenience method that uses the default demonstration_data base folder
    public static func getFolderURL(for recordingName: String) throws -> URL {
        let baseFolderURL = try getLocalDemoDataFolderURL()
        return try getFolderURL(for: recordingName, baseURL: baseFolderURL)
    }
    
    public static func getURL(recordingName: String, demonstrationSaveType: DemonstrationSaveType) throws -> URL {
        let folderURL = try getFolderURL(for: recordingName)
        
        switch demonstrationSaveType {
        case .JSON:
            return folderURL.appendingPathComponent("\(recordingName).json")
        case .RGB:
            return folderURL.appendingPathComponent("\(recordingName)_rgb.mp4")
        case .UltrawideRGB:
            return folderURL.appendingPathComponent("\(recordingName)_ultrawidergb.mp4")
        case .DepthMap:
            return folderURL.appendingPathComponent("\(recordingName)_depth.raw")
        case .DepthPreviewMap:
            return folderURL.appendingPathComponent("\(recordingName)_depthpreview.mp4")
        }
        
    }
    
    public func getURL(demonstrationSaveType: DemonstrationSaveType) throws -> URL {
        return try DemonstrationData.getURL(recordingName: recordingName, demonstrationSaveType: demonstrationSaveType)
    }
    
    public static func hasDataType(recordingName: String, demonstrationSaveType: DemonstrationSaveType) -> Bool {
        do {
            let fileURL = try DemonstrationData.getURL(recordingName: recordingName, demonstrationSaveType: demonstrationSaveType)
            let fileManager = FileManager.default
            return fileManager.fileExists(atPath: fileURL.path())
        } catch {
            return false
        }
    }
    
    func setFinalData(speechRecognitionResult: SFSpeechRecognitionResult?, transcriptionStartTime: Date?, taskSegmentationEvents: [TaskSegmentation]) {
        // speechRecognitionResult is only required if this is a demonstration and we are in narration mode
        var segmentationEvents = taskSegmentationEvents
        
        if type == .Demonstration {
            // if we do predefined tasks, then segmentationEvents is already fully ready to go
            // if we do language narration, then the segmentationEvents won't have the name or start time properties set (only the end time will be set), so we need to determine the start time and name based on the narration data
            
            // segment out subtasks from narration and segmentation events
            if labelType == .Narration {
                if speechRecognitionResult != nil {
                    // pull out the data from the speech result
                    var narrationStartTimestamps: [Date] = []
                    var narrationEndTimestamps: [Date] = []
                    
                    speechRecognitionResult?.bestTranscription.segments.forEach { segment in
                        // compute time offset including shift to UTC time at start of recording
                        let relativeStartTime = segment.timestamp
                        let textStartDate = transcriptionStartTime!.addingTimeInterval(relativeStartTime)
                        let textEndDate = textStartDate.addingTimeInterval(segment.duration)
                        
                        narrationStartTimestamps.append(textStartDate)
                        narrationEndTimestamps.append(textEndDate)
                        
                        self.narrationStartTimestamps.append(DateManager.getISOFormatter().string(from: textStartDate))
                        self.narrationEndTimestamps.append(DateManager.getISOFormatter().string(from: textEndDate))
                        narrationTexts.append(segment.substring)
                    }
                    
                    // segment out the subtasks from the narration data
                    var segmentStartIndex = 0
                    var subtaskIndex = 0
                    for index in narrationTexts.indices {
                        // if a command word is at the start of a segment, skip it so it doesn't become a task label
                        if (NarrationCommands.isStopWord(narrationTexts[index]) || NarrationCommands.isDoneWord(narrationTexts[index])) && segmentStartIndex == index {
                            segmentStartIndex += 1
                            continue
                        }
                        
                        let currentEndOfNarration = narrationEndTimestamps[index]
                        var isSubtaskDone = false
                        if index < narrationTexts.count - 1 {
                            // the narration times will set the end time of the previous segment to match the start time of the current segment if they are part of a contiguous command; any different between them means the last command has since ended and there was a gap before this word, thus the previous task is done. Sometimes small breaks are still introduced, so require at least half a second gap before considering a task done
                            let startOfNextNarration = narrationStartTimestamps[index+1]
                            isSubtaskDone = startOfNextNarration.timeIntervalSince(currentEndOfNarration) > 0.5
                            
                            // if a command word is next even if 0.5 seconds haven't passed, then we consider the subtask to be done. If the command word is said right after the start of the narration (no break), then just discard this subtask because it will have no data in it since it was stopped right away
                            if NarrationCommands.isStopWord(narrationTexts[index+1]) || NarrationCommands.isDoneWord(narrationTexts[index+1]) {
                                if startOfNextNarration.timeIntervalSince(currentEndOfNarration) == 0 {
                                    // no time past between when the task label ended and when the stop word started, so just cancel this subtask
                                    segmentStartIndex = index + 1
                                    continue
                                } else {
                                    // some time passed before the stop word was used, so even if it wasn't 0.5 seconds, consider the subtask to to be done
                                    isSubtaskDone = true
                                }
                            }
                        } else {
                            isSubtaskDone = true // this was the last language narration
                        }
                        
                        if isSubtaskDone {
                            // we have found a segment from startSegmentIndex to index, inclusive and we know the exact start time
                            
                            // the challenge is figuring out the exact end time. this can be from multiple sources
                            // source 1 is checking if there is a segmentation event with a taskEnd time that is AFTER currentEnd (i.e., right after the last word of the language annotation is spoken) and before the start of the next language annotation. There is a segmentation event for the end of the episode as well that can be used
                            // source 2 is if there is no segmentation events satisfying the requirement above, then we consider the end to be at the start of the next language label
                            
                            // we simplify all this logic, by just inserting a segmentation event at the start of each narration event and ignoring segmentation events if their end time is before the current narration's start time
                            
                            if index < narrationTexts.count - 1 {
                                // we know startOfNextNarration is part of a the next subtask label (not part of the current narration label)
                                let startOfNextNarration = narrationStartTimestamps[index+1]
                                
                                // insert a segmentation event ending at nextStart
                                let endNarrationEvent = TaskSegmentation()
                                endNarrationEvent.taskEnd = startOfNextNarration
                                
                                // insert the event in sorted order
                                var insertionIndex = subtaskIndex
                                while insertionIndex <= segmentationEvents.count {
                                    if insertionIndex == segmentationEvents.count {
                                        segmentationEvents.append(endNarrationEvent)
                                        break
                                    } else {
                                        if segmentationEvents[insertionIndex].taskEnd!.timeIntervalSince(endNarrationEvent.taskEnd!) > 0 { // meaning the entry currently there is later than the insertion value
                                            segmentationEvents.insert(endNarrationEvent, at: insertionIndex)
                                            break
                                        } else {
                                            insertionIndex += 1
                                        }
                                    }
                                }
                            }
                            
                            // loop through segmentation events until we have one that has an end time that is after the start time
                            while subtaskIndex < segmentationEvents.count && segmentationEvents[subtaskIndex].taskEnd!.timeIntervalSince(currentEndOfNarration) < 0 {
                                segmentationEvents.remove(at: subtaskIndex)
                            }

                            // no segmentation events left to assign this narration to
                            if subtaskIndex >= segmentationEvents.count { break }

                            segmentationEvents[subtaskIndex].taskStart = currentEndOfNarration
                            segmentationEvents[subtaskIndex].name = narrationTexts[segmentStartIndex...index].joined(separator: " ")
                            segmentStartIndex = index + 1
                            subtaskIndex += 1
                        }
                    }
                    while segmentationEvents.count > subtaskIndex {
                        segmentationEvents.removeLast()
                    }
                    
                    assert(subtaskIndex == segmentationEvents.count)
                } else {
                    // in this case narration mode was enabled, but no narration was detected, so cut the end task event
                    segmentationEvents = []
                }
            }
            
            // convert all of the segmentation events into the format stored in this class
            segmentationEvents.forEach { event in
                let startTime = DateManager.getISOFormatter().string(from: event.taskStart!)
                let endTime = DateManager.getISOFormatter().string(from: event.taskEnd!)
                let taskName = event.name!
                
                assert (event.taskEnd!.timeIntervalSince(event.taskStart!) > 0) // end has to be after start
                
                taskStartTimestamps.append(startTime)
                taskEndTimestamps.append(endTime)
                taskNames.append(taskName)
            }
        }
    }
    
    func saveLocally() throws {
        // validate that rgb video and ultrawide writers were initialized. This is needed since there is a weird edge case where if you take a really short video then perhaps a main camera frame has been received, but an ultrawide frame has not yet been received. In this case we just want to discard the demonstration
        if hasUltrawideRGB && ultrawideRGBVideoWriter == nil {
            throw RecordingError.ultrawideNotYetInitialized
        }
        
        // saves demonstration data to local storage
        let encoder = JSONEncoder()
        let data = try encoder.encode(self)
        let outfile = try getURL(demonstrationSaveType: .JSON)
        try data.write(to: outfile)
        
        let group = DispatchGroup()

        if hasRGB {
            group.enter()
            rgbVideoWriter!.finishWriting {
                let outURL = try? self.getURL(demonstrationSaveType: .RGB)
                print("Video writing finished: \(outURL!)")
                group.leave()
            }
        }

        if hasUltrawideRGB {
            group.enter()
            ultrawideRGBVideoWriter!.finishWriting {
                let outURL = try? self.getURL(demonstrationSaveType: .UltrawideRGB)
                print("Ultrawide video writing finished: \(outURL!)")
                group.leave()
            }
        }

        if depthVideoWriter != nil {
            depthVideoWriter!.finishWriting()
            let outURL = try? self.getURL(demonstrationSaveType: .DepthMap)
            print("Video writing finished: \(outURL!)")

            group.enter()
            depthPreviewVideoWriter!.finishWriting {
                let outURL = try? self.getURL(demonstrationSaveType: .DepthPreviewMap)
                print("Video writing finished: \(outURL!)")
                group.leave()
            }
        }

        group.wait()
    }
    
    /// Returns true if at least one file was newly copied (i.e. did not already exist at the destination).
    static func saveExternally(recordingName: String, directoryURL: URL) throws -> Bool {
        // copies the local save of this demonstration data to another location
        // should only be called after saveLocally is called
        // already-present files are skipped so a failed export can be resumed
        var anyNewFile = false
        for dataType in DemonstrationSaveType.allCases {
            if Self.hasDataType(recordingName: recordingName, demonstrationSaveType: dataType) {
                let file = try DemonstrationData.getURL(recordingName: recordingName, demonstrationSaveType: dataType)
                let destination = directoryURL.appendingPathComponent(file.lastPathComponent)
                if FileManager.default.fileExists(atPath: destination.path) {
                    continue
                }
                try FileManager.default.copyItem(at: file, to: destination)
                anyNewFile = true
            }
        }
        return anyNewFile
    }
    
    static func discard(recordingName: String) throws {
        // Remove the entire demonstration folder, which will delete all files within it
        let baseFolderURL = try getLocalDemoDataFolderURL()
        let folderURL = constructFolderURL(for: recordingName, baseURL: baseFolderURL)
        
        if FileManager.default.fileExists(atPath: folderURL.path) {
            try FileManager.default.removeItem(at: folderURL)
        }
    }
    
    static func discardDemonstrationsDir() throws {
        let rmdir = try Self.getLocalDemoDataFolderURL()
        if FileManager.default.fileExists(atPath: rmdir.path()) {
            try FileManager.default.removeItem(at: rmdir)
        }
    }
    
    static func listDemonstrations() throws -> [String] {
        // Get the base folder URL
        let baseFolderURL = try getLocalDemoDataFolderURL()
        let basePath = baseFolderURL.path
        
        var demonstrationNames: [String] = []
        
        // Check if base folder exists
        guard FileManager.default.fileExists(atPath: basePath) else {
            return demonstrationNames
        }
        
        // Get all date directories
        let dateDirs = try FileManager.default.contentsOfDirectory(atPath: basePath)
        
        // Traverse each date directory
        for dateDir in dateDirs {
            let dateDirPath = (basePath as NSString).appendingPathComponent(dateDir)
            
            // Check if it's a directory (not a file)
            var isDirectory: ObjCBool = false
            guard FileManager.default.fileExists(atPath: dateDirPath, isDirectory: &isDirectory), isDirectory.boolValue else {
                continue
            }
            
            // Get all demonstration name directories within this date directory
            let demonstrationDirs = try FileManager.default.contentsOfDirectory(atPath: dateDirPath)
            
            // Check each demonstration directory for JSON files
            for demonstrationDir in demonstrationDirs {
                let demonstrationDirPath = (dateDirPath as NSString).appendingPathComponent(demonstrationDir)
                
                // Check if it's a directory
                var isDemoDirectory: ObjCBool = false
                guard FileManager.default.fileExists(atPath: demonstrationDirPath, isDirectory: &isDemoDirectory), isDemoDirectory.boolValue else {
                    continue
                }
                
                // Look for JSON file matching the demonstration name
                let jsonFileName = "\(demonstrationDir).json"
                let jsonFilePath = (demonstrationDirPath as NSString).appendingPathComponent(jsonFileName)
                
                if FileManager.default.fileExists(atPath: jsonFilePath) {
                    demonstrationNames.append(demonstrationDir)
                }
            }
        }
        
        // Sort the names (newest first)
        demonstrationNames = demonstrationNames.sorted().reversed()
        
        return demonstrationNames
    }
    
    /// Returns the most recent gripper calibration recording name for the given session, or nil if none.
    /// Recording names use the format `..._sessionName_grippercalibration_...`; listDemonstrations() is already newest-first.
    static func mostRecentGripperCalibrationRunName(forSessionName sessionName: String) throws -> String? {
        let all = try listDemonstrations()
        let calibrationsForSession = all.filter { name in
            name.contains("_grippercalibration_") && name.contains("_\(sessionName)_")
        }
        return calibrationsForSession.first
    }
    
    /// Returns the gripperID stored in a calibration recording's JSON, or "default" if absent/unreadable.
    static func gripperIDForCalibration(recordingName: String) throws -> String {
        let jsonString = try loadAsString(recordingName: recordingName)
        guard let data = jsonString.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return "default"
        }
        return (json["gripperID"] as? String) ?? "default"
    }

    static func loadAsString(recordingName: String) throws -> String {
        let infile = try Self.getURL(recordingName: recordingName, demonstrationSaveType: .JSON)
        return try String(contentsOf: infile, encoding: .utf8)
    }
    
    /// Checks if a gripper calibration is referenced by any demonstrations
    /// - Parameter calibrationName: The name of the gripper calibration to check
    /// - Returns: true if the calibration is referenced by at least one demonstration, false otherwise
    static func isCalibrationReferenced(calibrationName: String) throws -> Bool {
        let allNames = try listDemonstrations()
        
        // Filter to only demonstrations (not calibrations)
        let demonstrationNames = allNames.filter { $0.contains("_demonstration_") }
        
        // Check each demonstration to see if it references this calibration
        for demoName in demonstrationNames {
            do {
                let jsonString = try loadAsString(recordingName: demoName)
                let jsonData = jsonString.data(using: .utf8)!
                let decoder = JSONDecoder()
                let demo = try decoder.decode(DemonstrationData.self, from: jsonData)
                
                if demo.gripperCalibrationRunName == calibrationName {
                    return true
                }
            } catch {
                // If we can't decode a demonstration, skip it and continue
                print("Failed to decode demonstration \(demoName): \(error)")
                continue
            }
        }
        
        return false
    }
    
}
