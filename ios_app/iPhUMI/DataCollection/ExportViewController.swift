//
//  ExportViewController.swift
//  iPhUMI
//

import Foundation
import UIKit

class ExportViewController: UIViewController, UIDocumentPickerDelegate {

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        let documentPicker = UIDocumentPickerViewController(forOpeningContentTypes: [.folder], asCopy: false)
        documentPicker.delegate = self
        present(documentPicker, animated: true)
    }

    func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
        dismiss(animated: true)
    }

    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
        guard let selectedFolderURL = urls.first else {
            dismiss(animated: true)
            return
        }

        let progressAlert = UIAlertController(title: "Exporting Data", message: "Please wait...", preferredStyle: .alert)
        let progressView = UIProgressView(progressViewStyle: .default)
        progressView.setProgress(0, animated: false)
        progressView.frame = CGRect(x: 10, y: 70, width: 250, height: 0)
        progressAlert.view.addSubview(progressView)
        let heightConstraint = NSLayoutConstraint(item: progressAlert.view!, attribute: .height, relatedBy: .equal, toItem: nil, attribute: .notAnAttribute, multiplier: 1, constant: 120)
        progressAlert.view.addConstraint(heightConstraint)

        present(progressAlert, animated: true)
        UIApplication.shared.isIdleTimerDisabled = true

        Task(priority: .userInitiated) {
            do {
                let demonstrationNames = try DemonstrationData.listDemonstrations()

                if demonstrationNames.isEmpty {
                    await MainActor.run {
                        progressAlert.dismiss(animated: true) {
                            UIApplication.shared.isIdleTimerDisabled = false
                            self.showResultAndDismiss(title: "No demonstrations to save")
                        }
                    }
                    return
                }

                let totalFiles = Float(demonstrationNames.count)
                var newCount = 0
                var alreadyExistedCount = 0
                var failedCount = 0

                for (index, demonstrationName) in demonstrationNames.enumerated() {
                    let coordinator = NSFileCoordinator()
                    var coordinationError: NSError?
                    var hadNewFile = false
                    var hadError = false

                    coordinator.coordinate(writingItemAt: selectedFolderURL, options: [.forReplacing], error: &coordinationError) { newURL in
                        if selectedFolderURL.startAccessingSecurityScopedResource() {
                            defer { selectedFolderURL.stopAccessingSecurityScopedResource() }
                            let baseExportURL = newURL.appending(path: "iPhUMI_export")
                            do {
                                let outputURL = try DemonstrationData.getFolderURL(for: demonstrationName, baseURL: baseExportURL)
                                hadNewFile = try DemonstrationData.saveExternally(recordingName: demonstrationName, directoryURL: outputURL)
                            } catch {
                                print("Error saving \(demonstrationName): \(error)")
                                hadError = true
                            }
                        }
                    }

                    if hadError {
                        failedCount += 1
                    } else if hadNewFile {
                        newCount += 1
                    } else {
                        alreadyExistedCount += 1
                    }

                    let progress = Float(index + 1) / totalFiles
                    await MainActor.run {
                        progressView.setProgress(progress, animated: true)
                        progressAlert.message = "Exporting \(index + 1) of \(demonstrationNames.count)...   "
                    }
                }

                let newCountCopy = newCount
                let alreadyExistedCountCopy = alreadyExistedCount
                let failedCountCopy = failedCount
                await MainActor.run {
                    progressAlert.dismiss(animated: true) {
                        UIApplication.shared.isIdleTimerDisabled = false
                        var message = "\(newCountCopy) newly exported"
                        if alreadyExistedCountCopy > 0 {
                            message += ", \(alreadyExistedCountCopy) already existed"
                        }
                        if failedCountCopy > 0 {
                            message += ", \(failedCountCopy) failed (storage full?)"
                        }
                        let title = failedCountCopy > 0 ? "Export incomplete" : "Export complete"
                        self.showResultAndDismiss(title: title, message: message)
                    }
                }

            } catch {
                await MainActor.run {
                    progressAlert.dismiss(animated: true) {
                        UIApplication.shared.isIdleTimerDisabled = false
                        self.showResultAndDismiss(title: "Failed to read demonstrations", message: error.localizedDescription)
                    }
                }
            }
        }
    }

    private func showResultAndDismiss(title: String, message: String = "") {
        let alert = UIAlertController(title: title, message: message, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default) { [weak self] _ in
            self?.dismiss(animated: true)
        })
        present(alert, animated: true)
    }
}
