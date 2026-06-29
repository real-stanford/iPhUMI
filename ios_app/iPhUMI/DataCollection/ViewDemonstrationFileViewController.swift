//
//  ViewDemonstrationFileViewController.swift
//  iPhUMI
//
//  Created by Austin Patel on 9/15/24.
//  Copyright © 2024 Apple. All rights reserved.
//

import Foundation
import UIKit
import AVKit

class ViewDemonstrationFileViewController: UIViewController {
    
    var documentInteractionController: UIDocumentInteractionController?
    
    @IBOutlet weak var viewJSONButton: UIButton!
    @IBOutlet weak var fileNameLabel: UILabel!
    @IBOutlet weak var viewVideoButton: UIButton!
    @IBOutlet weak var viewDepthButton: UIButton!
    @IBOutlet weak var viewUltrawideButton: UIButton!
    @IBOutlet weak var fileContentsTextView: UITextView!
    
    public var demonstrationName: String?
    
    public func initialize(demonstrationName: String) {
        // Load data from the file
        let jsonUrl = try? DemonstrationData.getURL(recordingName: demonstrationName, demonstrationSaveType: .JSON)
        let jsonData = try? Data(contentsOf: jsonUrl!)
        
        // show task narrations
        var subtasksPresent = false
        if let jsonObject = try? JSONSerialization.jsonObject(with: jsonData!, options: []) as? [String: Any] {
            if let taskNames = jsonObject["taskNames"] as? [String] {
                if taskNames.count > 0 {
                    subtasksPresent = true
                    
                    let formatter = DateManager.getISOFormatter()
                    let taskStartTimestamps = (jsonObject["taskStartTimestamps"] as? [String])!
                    let taskEndTimestamps = (jsonObject["taskEndTimestamps"] as? [String])!
                    let recordingStartTime = formatter.date(from: (jsonObject["recordingStartTime"] as? String)!)!
                    
                    var message = ""
                    for taskIndex in taskNames.indices {
                        if taskIndex > 0 {
                            message += "\n"
                        }
                        
                        // get start and end times (with respect to the start of the demonstration)
                        let startDate = formatter.date(from: taskStartTimestamps[taskIndex])!
                        let endDate = formatter.date(from: taskEndTimestamps[taskIndex])!
                        let relativeStartTime = startDate.timeIntervalSince(recordingStartTime)
                        let relativeEndTime = endDate.timeIntervalSince(recordingStartTime)
                        
                        let startTimeFormat = String(format: "%.2f", relativeStartTime)
                        let endTimeFormat = String(format: "%.2f", relativeEndTime)
                        message += "\(taskNames[taskIndex])  (start: \(startTimeFormat)s end: \(endTimeFormat)s)"
                    }
                    
                    fileContentsTextView.text = message
                }
            }
        }
        
        if !subtasksPresent {
            fileContentsTextView.text = "No subtasks found."
        }
        
        
        fileNameLabel.text = demonstrationName
        self.demonstrationName = demonstrationName
        
        viewVideoButton.isHidden = !DemonstrationData.hasDataType(recordingName: demonstrationName, demonstrationSaveType: .RGB)
        viewDepthButton.isHidden = !DemonstrationData.hasDataType(recordingName: demonstrationName, demonstrationSaveType: .DepthPreviewMap)
    }
    
    @IBAction func backButtonPressed(_ sender: Any) {
        self.dismiss(animated: true)
    }
    
    func playVideo(videoUrl: URL) {
        let player = AVPlayer(url: videoUrl)
                
        let vc = AVPlayerViewController()
        vc.player = player
        
        self.present(vc, animated: true) { vc.player?.play() }
    }
    
    @IBAction func viewJSONButtonPressed(_ sender: Any) {
        let url = try? DemonstrationData.getURL(recordingName: demonstrationName!, demonstrationSaveType: .JSON)
        openDocument(url: url!)
    }
    
    @IBAction func viewVideoButtonPressed(_ sender: Any) {
        let videoUrl = try? DemonstrationData.getURL(recordingName: demonstrationName!, demonstrationSaveType: .RGB)
        playVideo(videoUrl: videoUrl!)
    }
    
    @IBAction func viewUltrawideVideoButtonPressed(_ sender: Any) {
        let videoUrl = try? DemonstrationData.getURL(recordingName: demonstrationName!, demonstrationSaveType: .UltrawideRGB)
        playVideo(videoUrl: videoUrl!)
    }
    
    @IBAction func viewDepthButtonPressed(_ sender: Any) {
        let videoUrl = try? DemonstrationData.getURL(recordingName: demonstrationName!, demonstrationSaveType: .DepthPreviewMap)
        playVideo(videoUrl: videoUrl!)
    }
    
    func openDocument(url: URL) {
        documentInteractionController = UIDocumentInteractionController(url: url)
        documentInteractionController?.delegate = self
        documentInteractionController?.presentPreview(animated: true)
    }
    
}

extension ViewDemonstrationFileViewController: UIDocumentInteractionControllerDelegate {
    func documentInteractionControllerViewControllerForPreview(_ controller: UIDocumentInteractionController) -> UIViewController {
        return self
    }
}
