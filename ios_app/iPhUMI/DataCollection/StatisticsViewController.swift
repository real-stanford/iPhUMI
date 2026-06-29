//
//  StatisticsViewController.swift
//  iPhUMI
//
//  Created by Austin Patel on 5/5/25.
//  Copyright © 2025 Apple. All rights reserved.
//

import UIKit

class StatisticsViewController: UIViewController {

    var fnames: [String] = []

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        setupUI()
    }

    private func setupUI() {
        var backConfig = UIButton.Configuration.plain()
        backConfig.title = "Back"
        backConfig.image = UIImage(systemName: "chevron.backward")
        backConfig.imagePadding = 4
        let closeButton = UIButton(configuration: backConfig)
        closeButton.translatesAutoresizingMaskIntoConstraints = false
        closeButton.addTarget(self, action: #selector(closeTapped), for: .touchUpInside)
        view.addSubview(closeButton)

        let scrollView = UIScrollView()
        scrollView.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(scrollView)

        let stack = UIStackView()
        stack.axis = .vertical
        stack.spacing = 6
        stack.translatesAutoresizingMaskIntoConstraints = false
        scrollView.addSubview(stack)

        NSLayoutConstraint.activate([
            closeButton.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 12),
            closeButton.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor),

            scrollView.topAnchor.constraint(equalTo: closeButton.bottomAnchor, constant: 8),
            scrollView.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor),
            scrollView.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor),

            // Content constraints use contentLayoutGuide so the scroll view knows the content size
            stack.topAnchor.constraint(equalTo: scrollView.contentLayoutGuide.topAnchor, constant: 16),
            stack.leadingAnchor.constraint(equalTo: scrollView.contentLayoutGuide.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(equalTo: scrollView.contentLayoutGuide.trailingAnchor, constant: -20),
            stack.bottomAnchor.constraint(equalTo: scrollView.contentLayoutGuide.bottomAnchor, constant: -20),

            // Width matches the scroll view frame so only vertical scrolling occurs
            stack.widthAnchor.constraint(equalTo: scrollView.frameLayoutGuide.widthAnchor, constant: -40),
        ])

        let (taskCounts, sessionStats) = computeStats()

        stack.addArrangedSubview(makeLabel("Statistics", size: 22, weight: .bold, color: .white))
        stack.setCustomSpacing(20, after: stack.arrangedSubviews.last!)

        stack.addArrangedSubview(makeLabel("By Task", size: 17, weight: .semibold, color: .systemBlue))
        stack.setCustomSpacing(10, after: stack.arrangedSubviews.last!)
        if taskCounts.isEmpty {
            stack.addArrangedSubview(makeLabel("No task data available", size: 15, weight: .regular, color: .lightGray))
        } else {
            for (task, count) in taskCounts.sorted(by: { $0.key < $1.key }) {
                stack.addArrangedSubview(makeLabel("\(task): \(count)", size: 15, weight: .regular, color: .white))
            }
        }
        stack.setCustomSpacing(24, after: stack.arrangedSubviews.last!)

        stack.addArrangedSubview(makeLabel("By Session", size: 17, weight: .semibold, color: .systemBlue))
        stack.setCustomSpacing(10, after: stack.arrangedSubviews.last!)
        if sessionStats.isEmpty {
            stack.addArrangedSubview(makeLabel("No demonstrations", size: 15, weight: .regular, color: .lightGray))
        } else {
            for session in sessionStats.keys.sorted() {
                let stats = sessionStats[session]!
                stack.addArrangedSubview(makeLabel("\(session) (\(stats.totalDemos) demos)", size: 15, weight: .semibold, color: .white))
                for (task, count) in stats.taskCounts.sorted(by: { $0.key < $1.key }) {
                    stack.addArrangedSubview(makeLabel("  \(task): \(count)", size: 14, weight: .regular, color: .lightGray))
                }
                stack.setCustomSpacing(14, after: stack.arrangedSubviews.last!)
            }
        }
    }

    private struct SessionStats {
        var totalDemos: Int = 0
        var taskCounts: [String: Int] = [:]
    }

    private func computeStats() -> ([String: Int], [String: SessionStats]) {
        var taskCounts: [String: Int] = [:]
        var sessionStats: [String: SessionStats] = [:]

        for fname in fnames where fname.contains("_demonstration_") {
            let session = extractSession(from: fname)
            sessionStats[session, default: SessionStats()].totalDemos += 1

            for task in loadUniqueTaskNames(for: fname) {
                taskCounts[task, default: 0] += 1
                sessionStats[session, default: SessionStats()].taskCounts[task, default: 0] += 1
            }
        }

        return (taskCounts, sessionStats)
    }

    // Extracts the session name from a recording filename.
    // Format: YYYY-MM-DDTHH-MM-SS_NNNNN_SESSIONNAME_demonstration_SIDE
    private func extractSession(from fname: String) -> String {
        guard let markerRange = fname.range(of: "_demonstration_") else { return "unknown" }
        let prefix = String(fname[..<markerRange.lowerBound])
        let parts = prefix.components(separatedBy: "_")
        guard parts.count >= 3 else { return prefix }
        return parts.dropFirst(2).joined(separator: "_")
    }

    private func loadUniqueTaskNames(for recordingName: String) -> Set<String> {
        guard let jsonURL = try? DemonstrationData.getURL(recordingName: recordingName, demonstrationSaveType: .JSON),
              let data = try? Data(contentsOf: jsonURL),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let taskNames = json["taskNames"] as? [String] else {
            return []
        }
        return Set(taskNames)
    }

    @objc private func closeTapped() {
        dismiss(animated: true)
    }

    private func makeLabel(_ text: String, size: CGFloat, weight: UIFont.Weight, color: UIColor) -> UILabel {
        let label = UILabel()
        label.text = text
        label.textColor = color
        label.font = .systemFont(ofSize: size, weight: weight)
        label.numberOfLines = 0
        return label
    }
}
