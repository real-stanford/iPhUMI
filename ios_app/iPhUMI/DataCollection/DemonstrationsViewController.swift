//
//  DemonstrationsViewController.swift
//  iPhUMI
//
//  Created by Austin Patel on 9/13/24.
//  Copyright © 2024 Apple. All rights reserved.
//

import Foundation
import UIKit

class DemonstrationsViewController: UIViewController, UITableViewDataSource, UITableViewDelegate {
    
    @IBOutlet weak var titleLabel: UILabel!
    @IBOutlet weak var gripperCalibrationLabel: UILabel!
    @IBOutlet weak var tableView: UITableView!
    @IBOutlet weak var statisticsButton: UIButton!
    var fnames: [String] = []

    override func viewDidLoad() {
        super.viewDidLoad()
        
        // load all the data
        do {
            fnames = try DemonstrationData.listDemonstrations()
        } catch {
           print("failed to load demo data")
        }
        
        view.backgroundColor = .black
        tableView.backgroundColor = .black

        // Step 3: Set data source and delegate
        tableView.dataSource = self
        tableView.delegate = self
        
        // Register UITableViewCell class or a custom cell
        tableView.register(UITableViewCell.self, forCellReuseIdentifier: "cell")

        // Step 4: Add the table view to the view hierarchy
        self.view.addSubview(tableView)
        
        updateLabels()
    }

    // Step 5: Implement required UITableViewDataSource methods

    // Returns the number of rows in a section
    func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
        return fnames.count // Your data count here
    }

    // Returns the cell for a specific row at an index path
    func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = tableView.dequeueReusableCell(withIdentifier: "cell", for: indexPath)
        cell.textLabel?.text = "\(fnames[indexPath.row])"
        cell.backgroundColor = .black
        cell.textLabel?.textColor = .white
        return cell
    }

    // Optional: Handle table view row selection
    func tableView(_ tableView: UITableView, didSelectRowAt indexPath: IndexPath) {
        let storyboard = UIStoryboard(name: "Main", bundle: nil)
        let secondVC = storyboard.instantiateViewController(identifier: "ViewDemonstrationFileController") as ViewDemonstrationFileViewController
        
        secondVC.modalPresentationStyle = .fullScreen
        secondVC.modalTransitionStyle = .crossDissolve

        present(secondVC, animated: true, completion: nil)
        secondVC.initialize(demonstrationName: fnames[indexPath.row])
        
        tableView.deselectRow(at: indexPath, animated: true)
    }
    
    func tableView(_ tableView: UITableView, commit editingStyle: UITableViewCell.EditingStyle, forRowAt indexPath: IndexPath) {
        if editingStyle == .delete {
            let itemName = fnames[indexPath.row]
            
            // Check if this is a gripper calibration
            if itemName.contains("_grippercalibration_") {
                // Check if this calibration is referenced by any demonstrations
                do {
                    let isReferenced = try DemonstrationData.isCalibrationReferenced(calibrationName: itemName)
                    
                    if isReferenced {
                        // Show alert preventing deletion
                        let alert = UIAlertController(
                            title: "Cannot Delete Calibration",
                            message: "This gripper calibration cannot be deleted because it is referenced by one or more demonstrations.",
                            preferredStyle: .alert
                        )
                        alert.addAction(UIAlertAction(title: "OK", style: .default))
                        self.present(alert, animated: true)
                        return
                    }
                } catch {
                    print("Failed to check calibration references: \(error)")
                    // If we can't check, show an error but don't prevent deletion
                    let alert = UIAlertController(
                        title: "Error",
                        message: "Failed to check if calibration is referenced. Deletion cancelled.",
                        preferredStyle: .alert
                    )
                    alert.addAction(UIAlertAction(title: "OK", style: .default))
                    self.present(alert, animated: true)
                    return
                }
            }
            
            // Proceed with deletion
            do {
                try DemonstrationData.discard(recordingName: itemName)
                fnames = try DemonstrationData.listDemonstrations()
                
                // Update default gripper calibration if the deleted one was the default
                updateDefaultGripperCalibrationIfNeeded(deletedName: itemName)
                
                updateLabels()
                // Remove the row from the table view with an animation
                tableView.deleteRows(at: [indexPath], with: .automatic)
            } catch {
                print("failed to delete demonstration")
                let alert = UIAlertController(
                    title: "Error",
                    message: "Failed to delete demonstration.",
                    preferredStyle: .alert
                )
                alert.addAction(UIAlertAction(title: "OK", style: .default))
                self.present(alert, animated: true)
            }
        }
    }
    
    /// Updates the default gripper calibration if the deleted one was the current default.
    /// Uses the most recent gripper calibration for the current session only.
    func updateDefaultGripperCalibrationIfNeeded(deletedName: String) {
        let defaults = UserDefaults.standard
        let currentDefault = (defaults.object(forKey: "gripperCalibrationRunName") as? String) ?? ""
        
        guard deletedName == currentDefault else { return }
        
        let sessionName = (defaults.object(forKey: "sessionName") as? String) ?? "no-session"
        do {
            if let mostRecent = try DemonstrationData.mostRecentGripperCalibrationRunName(forSessionName: sessionName) {
                defaults.set(mostRecent, forKey: "gripperCalibrationRunName")
            } else {
                defaults.set("", forKey: "gripperCalibrationRunName")
            }
        } catch {
            defaults.set("", forKey: "gripperCalibrationRunName")
        }
    }
    
    func updateLabels() {
        // update gripper calibration run name - always use the value from UserDefaults
        let defaults = UserDefaults.standard
        let gripperCalibrationRunName = (defaults.object(forKey: "gripperCalibrationRunName") as? String) ?? ""
        let sessionName = (defaults.object(forKey: "sessionName") as? String) ?? "no-session"
        
        gripperCalibrationLabel.text = "Gripper Calibration (\"\(sessionName)\"): \(gripperCalibrationRunName)"
        
        // update demonstration count title
        var numDemonstrations = 0
        var numGripperCal = 0
        for fname in fnames {
            if fname.contains("_demonstration_") {
                numDemonstrations += 1
            } else if fname.contains("_grippercalibration_") {
                numGripperCal += 1
            }
        }
        titleLabel.text = "\(numDemonstrations) demos, \(numGripperCal) calibrations"
    }

    var onExportRequested: (() -> Void)?
    var onDismiss: (() -> Void)?

    @IBAction func exportButtonPressed(_ sender: Any) {
        let confirm = UIAlertController(
            title: "Export demonstrations",
            message: "You can connect an SD card using a USB-C to SD card adapter to the iPhone and select the SD card to export the demonstrations to. The export will create a folder called \"iPhUMI_export\" in the selected destination. If this folder already exists, the export will merge the new data in without overwriting existing data. To merge correctly, you should not click into the \"iPhUMI_export\" folder in the document picker, just open up the parent folder. The screen will remain on during the export.",
            preferredStyle: .alert
        )
        confirm.addAction(UIAlertAction(title: "OK", style: .default) { [weak self] _ in
            self?.onExportRequested?()
        })
        confirm.addAction(UIAlertAction(title: "Cancel", style: .cancel))
        present(confirm, animated: true)
    }

    @IBAction func backButtonPressed(_ sender: Any) {
        self.dismiss(animated: true) { [weak self] in
            self?.onDismiss?()
        }
    }

    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        if isBeingDismissed {
            onDismiss?()
        }
    }
    
    @IBAction func deleteAllButtonPressed(_ sender: Any) {
        let alert = UIAlertController(title: "Delete all demonstrations?", message: "Are you sure you want to delete all demonstrations and calibrations? This action can't be undone. You can delete individual demonstrations by swiping left on a list entry.", preferredStyle: .alert)

        // You can add actions using the following code
        alert.addAction(UIAlertAction(title: NSLocalizedString("Cancel", comment: "This closes alert"), style: .default, handler: { _ in
        NSLog("The \"OK\" alert occured.")
        }))
        alert.addAction(UIAlertAction(title: NSLocalizedString("Delete", comment: "This deletes all demonstrations"), style: .default, handler: { _ in
            do {
                try DemonstrationData.discardDemonstrationsDir()
            } catch {
                print("failed to delete demonstrations")
            }
            
            self.fnames = []
            
            // Clear the default gripper calibration since everything is deleted
            let defaults = UserDefaults.standard
            defaults.set("", forKey: "gripperCalibrationRunName")
            
            self.updateLabels()
            self.tableView.reloadData()
            
        }))

        // This part of code inits alert view
        self.present(alert, animated: true, completion: nil)
    }
    @IBAction func statisticsButtonPressed(_ sender: Any) {
        let statsVC = StatisticsViewController()
        statsVC.fnames = fnames
        statsVC.modalPresentationStyle = .fullScreen
        statsVC.modalTransitionStyle = .crossDissolve
        present(statsVC, animated: true)
    }
}
