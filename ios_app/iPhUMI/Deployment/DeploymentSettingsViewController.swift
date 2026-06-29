//
//  DeploymentSettingsViewController.swift
//  iPhUMI
//
//  Created by Austin Patel on 3/13/26.
//  Copyright © 2026 Apple. All rights reserved.
//

import UIKit
import Darwin
import Network

class DeploymentSettingsViewController: UITableViewController {

    var onDismiss: (() -> Void)?
    var onResetAndReturnHome: (() -> Void)?

    private var ethernetIPTimer: Timer?
    private let ethernetMonitor = NWPathMonitor(requiredInterfaceType: .wiredEthernet)
    private var wiredEthernetInterfaceNames: [String] = []

    private enum Section: Int, CaseIterable {
        case connection, camera, depth, interface
        var title: String {
            switch self {
            case .connection: return "Connection"
            case .camera: return "RGB Cameras"
            case .depth: return "Depth"
            case .interface: return "Interface"
            }
        }
    }

    private enum ConnectionRow: Int, CaseIterable { case connectionType, ethernetHostIP, iphoneEthernetIP }
    private enum CameraRow: Int, CaseIterable { case resolution, fps, autofocus, lensPosition, resetLensPosition }
    private enum DepthRow: Int, CaseIterable { case depthCapture, clippingDistance }
    private enum InterfaceRow: Int, CaseIterable { case preview }

    private var connectionTypeIndex: Int = 0
    private var resolutionIndex: Int = 0
    private var fpsIndex: Int = 1
    private var autofocusEnabled: Bool = false
    private var previewEnabled: Bool = true
    private var depthEnabled: Bool = false
    private var ethernetHostIP: String = "192.168.123.18"
    private var iphoneEthernetIP: String = "Disconnected"
    private var clippingDistance: Float = 1.0

    init() {
        super.init(style: .insetGrouped)
    }

    required init?(coder: NSCoder) { fatalError() }

    override func viewDidLoad() {
        super.viewDidLoad()
        title = "Deployment Settings"
        tableView.register(UITableViewCell.self, forCellReuseIdentifier: "cell")
        tableView.register(SegmentedControlCell.self, forCellReuseIdentifier: "segmented")
        navigationItem.rightBarButtonItem = UIBarButtonItem(barButtonSystemItem: .close, target: self, action: #selector(closeTapped))

        loadDefaults()

        ethernetMonitor.pathUpdateHandler = { [weak self] path in
            guard let self else { return }
            let names: [String] = path.status == .satisfied
                ? path.availableInterfaces.filter { $0.type == .wiredEthernet }.map { $0.name }
                : []
            DispatchQueue.main.async {
                self.wiredEthernetInterfaceNames = names
                self.refreshIphoneIP()
            }
        }
        ethernetMonitor.start(queue: DispatchQueue(label: "EthernetMonitorQueue"))
    }

    private func loadDefaults() {
        let defaults = UserDefaults.standard
        connectionTypeIndex = (defaults.object(forKey: "deployConnectionTypeIndex") as? Int) ?? 0
        resolutionIndex = (defaults.object(forKey: "deployStreamResolutionIndex") as? Int) ?? 0
        fpsIndex = (defaults.object(forKey: "deployCameraFPSIndex") as? Int) ?? 1
        autofocusEnabled = (defaults.object(forKey: "deployUltrawideAutofocus") as? Bool) ?? false
        previewEnabled = (defaults.object(forKey: "deployEnablePreview") as? Bool) ?? true
        depthEnabled = (defaults.object(forKey: "deployEnableDepth") as? Bool) ?? false
        ethernetHostIP = defaults.string(forKey: "deployEthernetHostIP") ?? "192.168.123.18"
        clippingDistance = (defaults.object(forKey: "deployDepthPreviewClippingDistance") as? Float) ?? 1.0
    }

    private func refreshIphoneIP() {
        iphoneEthernetIP = getEthernetAdapterIPAddress() ?? "Disconnected"
        let ip = IndexPath(row: ConnectionRow.iphoneEthernetIP.rawValue, section: Section.connection.rawValue)
        tableView.reloadRows(at: [ip], with: .none)
    }

    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        refreshIphoneIP()
        ethernetIPTimer?.invalidate()
        ethernetIPTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            self?.refreshIphoneIP()
        }
    }

    override func viewDidDisappear(_ animated: Bool) {
        super.viewDidDisappear(animated)
        ethernetIPTimer?.invalidate()
        ethernetIPTimer = nil
        if isBeingDismissed || isMovingFromParent || parent?.isBeingDismissed == true {
            onDismiss?()
        }
    }

    // MARK: - Table view

    override func numberOfSections(in tableView: UITableView) -> Int { Section.allCases.count }

    override func tableView(_ tableView: UITableView, titleForHeaderInSection section: Int) -> String? {
        Section(rawValue: section)?.title
    }

    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
        switch Section(rawValue: section)! {
        case .connection: return ConnectionRow.allCases.count
        case .camera: return CameraRow.allCases.count
        case .depth: return DepthRow.allCases.count
        case .interface: return InterfaceRow.allCases.count
        }
    }

    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        switch Section(rawValue: indexPath.section)! {

        case .connection:
            switch ConnectionRow(rawValue: indexPath.row)! {
            case .connectionType:
                let cell = tableView.dequeueReusableCell(withIdentifier: "segmented", for: indexPath) as! SegmentedControlCell
                cell.configure(label: "Connection Type", segments: ["USB", "Ethernet"],
                               selectedIndex: connectionTypeIndex,
                               target: self, action: #selector(connectionTypeChanged(_:)))
                return cell
            case .ethernetHostIP:
                let cell = UITableViewCell(style: .value1, reuseIdentifier: nil)
                cell.textLabel?.text = "Ethernet Host IP"
                cell.detailTextLabel?.text = ethernetHostIP
                cell.accessoryType = .disclosureIndicator
                return cell
            case .iphoneEthernetIP:
                let cell = UITableViewCell(style: .value1, reuseIdentifier: nil)
                cell.textLabel?.text = "iPhone Ethernet IP"
                cell.detailTextLabel?.text = iphoneEthernetIP
                cell.accessoryType = .disclosureIndicator
                return cell
            }

        case .camera:
            switch CameraRow(rawValue: indexPath.row)! {
            case .resolution:
                let cell = tableView.dequeueReusableCell(withIdentifier: "segmented", for: indexPath) as! SegmentedControlCell
                cell.configure(label: "RGB Resolution", segments: ["Low (320×240)", "High (960×720)"],
                               selectedIndex: resolutionIndex,
                               target: self, action: #selector(resolutionChanged(_:)))
                return cell
            case .fps:
                let cell = tableView.dequeueReusableCell(withIdentifier: "segmented", for: indexPath) as! SegmentedControlCell
                cell.configure(label: "RGB FPS", segments: ["30 fps", "60 fps"],
                               selectedIndex: fpsIndex,
                               target: self, action: #selector(fpsChanged(_:)))
                return cell
            case .autofocus:
                let cell = UITableViewCell(style: .subtitle, reuseIdentifier: nil)
                cell.textLabel?.text = "Ultrawide Autofocus"
                cell.detailTextLabel?.text = "For policy deployment, keep autofocus disabled to match what ARKit does (locked to the stored lens position below). You might want to enable this for a third person camera for logging so that it will keep the subject in focus."
                cell.detailTextLabel?.textColor = .secondaryLabel
                cell.detailTextLabel?.numberOfLines = 0
                cell.selectionStyle = .none
                let toggle = UISwitch()
                toggle.isOn = autofocusEnabled
                toggle.addTarget(self, action: #selector(autofocusToggled(_:)), for: .valueChanged)
                cell.accessoryView = toggle
                return cell
            case .lensPosition:
                let cell = UITableViewCell(style: .subtitle, reuseIdentifier: nil)
                cell.selectionStyle = .none
                let stored = UserDefaults.standard.object(forKey: "arKitUltrawideLensPosition") as? Float
                let valueStr = stored.map { String(format: "%.7f", $0) } ?? "Not yet set"
                cell.textLabel?.text = "Ultrawide Lens Position: \(valueStr)"
                cell.detailTextLabel?.text = "Main camera uses auto-focus and ultrawide does not (matching what ARKit does); ultrawide is locked to this fixed position captured from ARKit to match ARKit setup (note it's often a little blurry but it's better if it's consistent between train and test). Ignored when autofocus is enabled above."
                cell.detailTextLabel?.textColor = .secondaryLabel
                cell.detailTextLabel?.numberOfLines = 0
                return cell
            case .resetLensPosition:
                let cell = UITableViewCell(style: .default, reuseIdentifier: nil)
                cell.textLabel?.text = "Reset Ultrawide Lens Position & Return Home"
                cell.textLabel?.textColor = .systemRed
                cell.textLabel?.textAlignment = .center
                return cell
            }

        case .depth:
            switch DepthRow(rawValue: indexPath.row)! {
            case .depthCapture:
                let cell = UITableViewCell(style: .default, reuseIdentifier: nil)
                cell.textLabel?.text = "Depth Capture"
                cell.selectionStyle = .none
                let toggle = UISwitch()
                toggle.isOn = depthEnabled
                toggle.addTarget(self, action: #selector(depthToggled(_:)), for: .valueChanged)
                cell.accessoryView = toggle
                return cell
            case .clippingDistance:
                let cell = UITableViewCell(style: .subtitle, reuseIdentifier: nil)
                cell.textLabel?.text = "Preview Clipping Distance: \(String(format: "%.2f m", clippingDistance))"
                cell.detailTextLabel?.text = "Only impacts the preview — does not affect transmitted depth data"
                cell.detailTextLabel?.textColor = .secondaryLabel
                cell.accessoryType = .disclosureIndicator
                return cell
            }

        case .interface:
            switch InterfaceRow(rawValue: indexPath.row)! {
            case .preview:
                let cell = UITableViewCell(style: .subtitle, reuseIdentifier: nil)
                cell.textLabel?.text = "Camera Preview"
                cell.detailTextLabel?.text = "Enabling preview might reduce streaming performance"
                cell.detailTextLabel?.textColor = .secondaryLabel
                cell.selectionStyle = .none
                let toggle = UISwitch()
                toggle.isOn = previewEnabled
                toggle.addTarget(self, action: #selector(previewToggled(_:)), for: .valueChanged)
                cell.accessoryView = toggle
                return cell
            }

        }
    }

    override func tableView(_ tableView: UITableView, didSelectRowAt indexPath: IndexPath) {
        tableView.deselectRow(at: indexPath, animated: true)
        switch Section(rawValue: indexPath.section)! {
        case .connection:
            switch ConnectionRow(rawValue: indexPath.row)! {
            case .ethernetHostIP: showEthernetHostIPAlert()
            case .iphoneEthernetIP:
                if let url = URL(string: "App-Prefs:") {
                    UIApplication.shared.open(url)
                }
            default: break
            }
        case .camera:
            if CameraRow(rawValue: indexPath.row) == .resetLensPosition {
                let confirm = UIAlertController(
                    title: "Reset Ultrawide Lens Position",
                    message: "This will clear the saved ultrawide lens position and return to the home screen. You will need to open the Data Collection interface again before using Deployment.",
                    preferredStyle: .alert
                )
                confirm.addAction(UIAlertAction(title: "Cancel", style: .cancel))
                confirm.addAction(UIAlertAction(title: "Reset", style: .destructive) { [weak self] _ in
                    UserDefaults.standard.removeObject(forKey: "arKitUltrawideLensPosition")
                    self?.dismiss(animated: true) {
                        self?.onResetAndReturnHome?()
                    }
                })
                present(confirm, animated: true)
            }
        case .depth:
            if DepthRow(rawValue: indexPath.row) == .clippingDistance {
                showClippingDistanceAlert()
            }
        default: break
        }
    }

    // MARK: - Actions

    @objc private func connectionTypeChanged(_ sender: UISegmentedControl) {
        connectionTypeIndex = sender.selectedSegmentIndex
        UserDefaults.standard.set(connectionTypeIndex, forKey: "deployConnectionTypeIndex")
    }

    @objc private func resolutionChanged(_ sender: UISegmentedControl) {
        resolutionIndex = sender.selectedSegmentIndex
        UserDefaults.standard.set(resolutionIndex, forKey: "deployStreamResolutionIndex")
    }

    @objc private func fpsChanged(_ sender: UISegmentedControl) {
        fpsIndex = sender.selectedSegmentIndex
        UserDefaults.standard.set(fpsIndex, forKey: "deployCameraFPSIndex")
    }

    @objc private func autofocusToggled(_ sender: UISwitch) {
        autofocusEnabled = sender.isOn
        UserDefaults.standard.set(autofocusEnabled, forKey: "deployUltrawideAutofocus")
    }

    @objc private func previewToggled(_ sender: UISwitch) {
        previewEnabled = sender.isOn
        UserDefaults.standard.set(previewEnabled, forKey: "deployEnablePreview")
    }

    @objc private func depthToggled(_ sender: UISwitch) {
        depthEnabled = sender.isOn
        UserDefaults.standard.set(depthEnabled, forKey: "deployEnableDepth")
    }

    @objc private func closeTapped() {
        dismiss(animated: true)
    }

    // MARK: - Alerts

    private func showEthernetHostIPAlert() {
        let alert = UIAlertController(
            title: "Ethernet Host IP",
            message: "Enter the IP address of the host for Ethernet streaming.",
            preferredStyle: .alert
        )
        alert.addTextField { field in
            field.keyboardType = .numbersAndPunctuation
            field.placeholder = "192.168.123.18"
            field.text = self.ethernetHostIP
        }
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
        alert.addAction(UIAlertAction(title: "Save", style: .default) { [weak self] _ in
            guard let self else { return }
            let raw = alert.textFields?.first?.text ?? ""
            let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            let final = value.isEmpty ? "192.168.123.18" : value
            guard Self.isValidIPv4Address(final) else {
                let err = UIAlertController(title: "Invalid IP Address",
                                            message: "Please enter a valid IPv4 address, e.g. 192.168.123.18.",
                                            preferredStyle: .alert)
                err.addAction(UIAlertAction(title: "OK", style: .default))
                self.present(err, animated: true)
                return
            }
            self.ethernetHostIP = final
            UserDefaults.standard.set(final, forKey: "deployEthernetHostIP")
            let row = IndexPath(row: ConnectionRow.ethernetHostIP.rawValue, section: Section.connection.rawValue)
            self.tableView.reloadRows(at: [row], with: .none)
        })
        present(alert, animated: true)
    }

    private func showClippingDistanceAlert() {
        let alert = UIAlertController(
            title: "Depth Preview Clipping Distance",
            message: "Enter the maximum distance (in meters) to visualize. Must be between 0.5 and 10 meters. This only affects the preview on the iPhone, not the actual depth data streamed.",
            preferredStyle: .alert
        )
        alert.addTextField { field in
            field.keyboardType = .decimalPad
            field.placeholder = "1.0"
            field.text = String(format: "%.2f", self.clippingDistance)
        }
        alert.addAction(UIAlertAction(title: "Cancel", style: .cancel))
        alert.addAction(UIAlertAction(title: "Save", style: .default) { [weak self] _ in
            guard let self else { return }
            let raw = alert.textFields?.first?.text ?? ""
            guard let value = Float(raw.trimmingCharacters(in: .whitespacesAndNewlines)),
                  value >= 0.5, value <= 10.0 else {
                let err = UIAlertController(title: "Invalid Value",
                                            message: "Please enter a number between 0.5 and 10 meters.",
                                            preferredStyle: .alert)
                err.addAction(UIAlertAction(title: "OK", style: .default))
                self.present(err, animated: true)
                return
            }
            self.clippingDistance = value
            UserDefaults.standard.set(value, forKey: "deployDepthPreviewClippingDistance")
            let row = IndexPath(row: DepthRow.clippingDistance.rawValue, section: Section.depth.rawValue)
            self.tableView.reloadRows(at: [row], with: .none)
        })
        present(alert, animated: true)
    }

    // MARK: - Helpers

    private static func isValidIPv4Address(_ string: String) -> Bool {
        let parts = string.split(separator: ".")
        guard parts.count == 4 else { return false }
        return parts.allSatisfy { Int($0).map { $0 >= 0 && $0 <= 255 } ?? false }
    }

    private func getEthernetAdapterIPAddress() -> String? {
        var address: String?
        var ifaddr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddr) == 0, let firstAddr = ifaddr else { return nil }
        defer { freeifaddrs(ifaddr) }

        for ptr in sequence(first: firstAddr, next: { $0.pointee.ifa_next }) {
            let interface = ptr.pointee
            guard let addr = interface.ifa_addr, addr.pointee.sa_family == sa_family_t(AF_INET) else { continue }
            let ifName = String(cString: interface.ifa_name)
            let isWiredFromMonitor = wiredEthernetInterfaceNames.contains(ifName)
            let isWiredHeuristic = ifName.hasPrefix("en") && ifName != "en0"
            guard (!wiredEthernetInterfaceNames.isEmpty && isWiredFromMonitor) ||
                  (wiredEthernetInterfaceNames.isEmpty && isWiredHeuristic) else { continue }
            var hostname = [CChar](repeating: 0, count: Int(INET_ADDRSTRLEN))
            var addr4 = unsafeBitCast(addr.pointee, to: sockaddr_in.self)
            inet_ntop(AF_INET, &addr4.sin_addr, &hostname, socklen_t(INET_ADDRSTRLEN))
            address = String(cString: hostname)
            break
        }
        return address
    }
}

// MARK: - Segmented control cell

private class SegmentedControlCell: UITableViewCell {
    let label = UILabel()
    let segmentedControl = UISegmentedControl()

    override init(style: UITableViewCell.CellStyle, reuseIdentifier: String?) {
        super.init(style: style, reuseIdentifier: reuseIdentifier)
        selectionStyle = .none
        let stack = UIStackView(arrangedSubviews: [label, segmentedControl])
        stack.axis = .vertical
        stack.spacing = 8
        stack.translatesAutoresizingMaskIntoConstraints = false
        contentView.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: contentView.topAnchor, constant: 12),
            stack.bottomAnchor.constraint(equalTo: contentView.bottomAnchor, constant: -12),
            stack.leadingAnchor.constraint(equalTo: contentView.leadingAnchor, constant: 16),
            stack.trailingAnchor.constraint(equalTo: contentView.trailingAnchor, constant: -16)
        ])
        label.font = UIFont.preferredFont(forTextStyle: .body)
    }

    required init?(coder: NSCoder) { fatalError() }

    func configure(label: String, segments: [String], selectedIndex: Int, target: Any?, action: Selector) {
        self.label.text = label
        segmentedControl.removeAllSegments()
        segmentedControl.removeTarget(nil, action: nil, for: .valueChanged)
        for (i, title) in segments.enumerated() {
            segmentedControl.insertSegment(withTitle: title, at: i, animated: false)
        }
        segmentedControl.selectedSegmentIndex = selectedIndex
        segmentedControl.addTarget(target, action: action, for: .valueChanged)
    }
}
