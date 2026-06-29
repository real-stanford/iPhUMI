//
//  RootViewController.swift
//  iPhUMI
//
//  Created by Austin Patel on 1/31/25.
//  Copyright © 2025 Apple. All rights reserved.
//

import UIKit

class RootViewController: UIViewController {
        
    @IBOutlet weak var versionLabel: UILabel!
    override func viewDidLoad() {
        super.viewDidLoad()
        let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
        let bundleID = Bundle.main.bundleIdentifier ?? "unknown"
        versionLabel.text = "\(bundleID) · v\(version)"
    }
    
    override func viewDidAppear(_ animated: Bool) {
        let defaults = UserDefaults.standard
        var appMode = defaults.object(forKey: "appMode") as? String
        
        if appMode == "demonstration" {
            collectDemonstration()
        } else if appMode == "deployment" {
            startDeployment()
        }
    }
    
    func collectDemonstration() {
        let defaults = UserDefaults.standard
        defaults.set("demonstration", forKey: "appMode")
        
        let storyboard = UIStoryboard(name: "Main", bundle: nil)
        let secondVC = storyboard.instantiateViewController(identifier: "DemonstrationViewController")

        secondVC.modalPresentationStyle = .fullScreen
        secondVC.modalTransitionStyle = .crossDissolve

        present(secondVC, animated: true, completion: nil)
    }
    
    func startDeployment() {
        guard UserDefaults.standard.object(forKey: "arKitUltrawideLensPosition") != nil else {
            UserDefaults.standard.removeObject(forKey: "appMode")
            let alert = UIAlertController(
                title: "Camera Not Initialized",
                message: "Camera parameters have not been initialized yet. Please open the Data Collection interface first so ARKit can run and calibrate the camera, then return here to start deployment.",
                preferredStyle: .alert
            )
            alert.addAction(UIAlertAction(title: "OK", style: .default))
            present(alert, animated: true)
            return
        }

        let defaults = UserDefaults.standard
        defaults.set("deployment", forKey: "appMode")

        let storyboard = UIStoryboard(name: "Main", bundle: nil)
        let secondVC = storyboard.instantiateViewController(identifier: "DeploymentViewController")

        secondVC.modalPresentationStyle = .fullScreen
        secondVC.modalTransitionStyle = .crossDissolve

        present(secondVC, animated: true, completion: nil)
    }
    @IBAction func collectDemonstrationButtonPress(_ sender: Any) {
        collectDemonstration()
    }
    @IBAction func startDeploymentButtonPress(_ sender: Any) {
        startDeployment()
    }
}
