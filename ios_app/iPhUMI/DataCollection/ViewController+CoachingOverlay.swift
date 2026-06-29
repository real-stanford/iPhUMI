/*
See LICENSE folder for this sample’s licensing information.

Abstract:
Methods on the main view controller for conforming to the ARCoachingOverlayViewDelegate protocol.
*/

import UIKit
import ARKit

extension ViewController: ARCoachingOverlayViewDelegate {
    
    func coachingOverlayViewWillActivate(_ coachingOverlayView: ARCoachingOverlayView) {
//        messageLabel.ignoreMessages = true
//        messageLabel.isHidden = true
        
//        for view in arView.subviews {
//            view.isHidden = true
//        }
    }

    func coachingOverlayViewDidDeactivate(_ coachingOverlayView: ARCoachingOverlayView) {
//        messageLabel.ignoreMessages = false
        
//        for view in arView.subviews {
//            view.isHidden = false
//        }
//        messageLabel.isHidden = true
    }

    func coachingOverlayViewDidRequestSessionReset(_ coachingOverlayView: ARCoachingOverlayView) {
        resetAll()
    }

    func setupCoachingOverlay() {
        if !useViewer {
            return
        }
        
        let arView = arView!
        let coachingOverlay = coachingOverlay!
        
        // Set up coaching view
        coachingOverlay.session = arView.session
        coachingOverlay.delegate = self
        coachingOverlay.goal = .tracking
        
        coachingOverlay.translatesAutoresizingMaskIntoConstraints = false
        arView.addSubview(coachingOverlay)
        
        NSLayoutConstraint.activate([
            coachingOverlay.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            coachingOverlay.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            coachingOverlay.widthAnchor.constraint(equalTo: view.widthAnchor),
            coachingOverlay.heightAnchor.constraint(equalTo: view.heightAnchor)
            ])
    }
}
