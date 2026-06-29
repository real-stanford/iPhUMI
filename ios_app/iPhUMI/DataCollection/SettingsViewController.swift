import UIKit

class SettingsViewController: UITableViewController {

    var onViewerToggled: ((Bool) -> Void)?
    var onMultipeerToggled: ((Bool) -> Void)?
    var onSpeechRecognizerToggled: ((Bool) -> Void)?
    var onMultipeerVoiceHostToggled: ((Bool) -> Void)?
    var onManualPeerSync: (() -> Void)?
    var onErrorCorrectionToggled: ((Bool) -> Void)?
    var isPeerConnected: (() -> Bool)?

    private var viewerEnabled: Bool
    private var multipeerEnabled: Bool
    private var speechRecognizerEnabled: Bool
    private var multipeerVoiceHost: Bool
    private var errorCorrectionEnabled: Bool

    private enum Section: Int, CaseIterable {
        case general, multipeer
        var title: String {
            switch self {
            case .general: return "General"
            case .multipeer: return "Multipeer"
            }
        }
    }

    private enum GeneralRow: Int, CaseIterable { case viewer, speechRecognizer, errorCorrection }
    private enum MultipeerRow: Int, CaseIterable { case multipeer, multipeerVoiceHost, peerSync }

    init() {
        let defaults = UserDefaults.standard
        viewerEnabled = defaults.object(forKey: "useViewer") as? Bool ?? false
        multipeerEnabled = defaults.object(forKey: "multipeerEnabled") as? Bool ?? true
        speechRecognizerEnabled = defaults.object(forKey: "speechRecognizerEnabled") as? Bool ?? true
        multipeerVoiceHost = defaults.object(forKey: "multipeerVoiceHost") as? Bool ?? false
        errorCorrectionEnabled = defaults.object(forKey: "errorCorrectionMode") as? Bool ?? false
        super.init(style: .insetGrouped)
    }

    required init?(coder: NSCoder) { fatalError() }

    override func viewDidLoad() {
        super.viewDidLoad()
        title = "Settings"
        tableView.register(UITableViewCell.self, forCellReuseIdentifier: "cell")
        tableView.rowHeight = UITableView.automaticDimension
        tableView.estimatedRowHeight = 60
        navigationItem.rightBarButtonItem = UIBarButtonItem(barButtonSystemItem: .close, target: self, action: #selector(closeTapped))
    }

    // MARK: - Table view

    override func numberOfSections(in tableView: UITableView) -> Int { Section.allCases.count }

    override func tableView(_ tableView: UITableView, titleForHeaderInSection section: Int) -> String? {
        Section(rawValue: section)?.title
    }

    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
        switch Section(rawValue: section)! {
        case .general: return GeneralRow.allCases.count
        case .multipeer: return MultipeerRow.allCases.count
        }
    }

    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = UITableViewCell(style: .subtitle, reuseIdentifier: "cell")
        cell.selectionStyle = .none
        cell.detailTextLabel?.numberOfLines = 0

        switch Section(rawValue: indexPath.section)! {

        case .general:
            switch GeneralRow(rawValue: indexPath.row)! {
            case .viewer:
                cell.textLabel?.text = "Enable Viewer"
                cell.detailTextLabel?.text = "Enabling the viewer will substantially degrade performance"
                cell.detailTextLabel?.textColor = .secondaryLabel
                let toggle = UISwitch()
                toggle.isOn = viewerEnabled
                toggle.addTarget(self, action: #selector(viewerToggled(_:)), for: .valueChanged)
                cell.accessoryView = toggle

            case .speechRecognizer:
                cell.textLabel?.text = "Enable Voice Commands"
                let startWords = NarrationCommands.startWords.map { "\"\($0)\"" }.joined(separator: ", ")
                let stopWords = NarrationCommands.stopWords.map { "\"\($0)\"" }.joined(separator: ", ")
                let doneWords = NarrationCommands.doneWords.map { "\"\($0)\"" }.joined(separator: ", ")
                let deleteWords = NarrationCommands.deleteWords.map { "\"\($0)\"" }.joined(separator: ", ")
                cell.detailTextLabel?.text = "You can say commands out loud to start/stop recordings.\nStart words (starts recording): \(startWords)\nStop words (ends recording): \(stopWords)\nDelete words (deletes the previous recording): \(deleteWords)\nDone words (narration mode only; marks previous task as complete without stopping recording): \(doneWords)\nIf using multipeer, make sure that only one device has this enabled to avoid conflicts."
                cell.detailTextLabel?.textColor = .secondaryLabel
                let toggle = UISwitch()
                toggle.isOn = speechRecognizerEnabled
                toggle.addTarget(self, action: #selector(speechRecognizerToggled(_:)), for: .valueChanged)
                cell.accessoryView = toggle

            case .errorCorrection:
                cell.textLabel?.text = "Error Correction Mode"
                cell.detailTextLabel?.text = "Mark recordings as error correction data. When enabled in demonstration mode, the record button text will turn red."
                cell.detailTextLabel?.textColor = .secondaryLabel
                let toggle = UISwitch()
                toggle.isOn = errorCorrectionEnabled
                toggle.addTarget(self, action: #selector(errorCorrectionToggled(_:)), for: .valueChanged)
                cell.accessoryView = toggle
            }

        case .multipeer:
            switch MultipeerRow(rawValue: indexPath.row)! {
            case .multipeer:
                cell.textLabel?.text = "Enable Multipeer Connectivity"
                cell.detailTextLabel?.text = "Whether this device will connect to others for multi-device data collection"
                cell.detailTextLabel?.textColor = .secondaryLabel
                let toggle = UISwitch()
                toggle.isOn = multipeerEnabled
                toggle.addTarget(self, action: #selector(multipeerToggled(_:)), for: .valueChanged)
                cell.accessoryView = toggle

            case .multipeerVoiceHost:
                cell.textLabel?.text = "Multipeer Voice Host"
                cell.detailTextLabel?.text = "In narration mode with multiple devices, exactly one device must have this enabled. If enabled, it means we will use this device as the authoritative source of narration labels. You also want to make sure \"Enable Voice Commands\" is not enabled on multiple devices, otherwise there will be conflicts."
                cell.detailTextLabel?.textColor = .secondaryLabel
                let toggle = UISwitch()
                toggle.isOn = multipeerVoiceHost
                toggle.addTarget(self, action: #selector(multipeerVoiceHostToggled(_:)), for: .valueChanged)
                cell.accessoryView = toggle

            case .peerSync:
                let peersConnected = isPeerConnected?() ?? false
                cell.textLabel?.text = "Manual Peer Sync"
                cell.textLabel?.textColor = peersConnected ? .label : .tertiaryLabel
                cell.detailTextLabel?.text = "Note this is already automatically done when each recording starts"
                cell.detailTextLabel?.textColor = .secondaryLabel
                cell.selectionStyle = peersConnected ? .default : .none
                cell.accessoryType = peersConnected ? .disclosureIndicator : .none
            }
        }

        return cell
    }

    override func tableView(_ tableView: UITableView, didSelectRowAt indexPath: IndexPath) {
        tableView.deselectRow(at: indexPath, animated: true)
        guard Section(rawValue: indexPath.section) == .multipeer,
              MultipeerRow(rawValue: indexPath.row) == .peerSync else { return }
        guard isPeerConnected?() == true else { return }
        onManualPeerSync?()
        let alert = UIAlertController(title: "Settings Synced", message: "Settings have been pushed to all connected peers.", preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        present(alert, animated: true)
    }

    // MARK: - Actions

    @objc private func viewerToggled(_ sender: UISwitch) {
        viewerEnabled = sender.isOn
        UserDefaults.standard.set(viewerEnabled, forKey: "useViewer")
        onViewerToggled?(viewerEnabled)
    }

    @objc private func multipeerToggled(_ sender: UISwitch) {
        multipeerEnabled = sender.isOn
        UserDefaults.standard.set(multipeerEnabled, forKey: "multipeerEnabled")
        onMultipeerToggled?(multipeerEnabled)
    }

    @objc private func speechRecognizerToggled(_ sender: UISwitch) {
        speechRecognizerEnabled = sender.isOn
        UserDefaults.standard.set(speechRecognizerEnabled, forKey: "speechRecognizerEnabled")
        onSpeechRecognizerToggled?(speechRecognizerEnabled)
    }

    @objc private func multipeerVoiceHostToggled(_ sender: UISwitch) {
        multipeerVoiceHost = sender.isOn
        UserDefaults.standard.set(multipeerVoiceHost, forKey: "multipeerVoiceHost")
        onMultipeerVoiceHostToggled?(multipeerVoiceHost)
    }

    @objc private func errorCorrectionToggled(_ sender: UISwitch) {
        errorCorrectionEnabled = sender.isOn
        UserDefaults.standard.set(errorCorrectionEnabled, forKey: "errorCorrectionMode")
        onErrorCorrectionToggled?(errorCorrectionEnabled)
    }

    @objc private func closeTapped() {
        dismiss(animated: true)
    }
}
