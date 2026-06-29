//
//  TasksViewController.swift
//  iPhUMI
//
//  Created by Austin Patel on 1/11/25.
//  Copyright © 2025 Apple. All rights reserved.
//

import UIKit

class TaskCell: UITableViewCell {
    let textField: UITextField = {
        let textField = UITextField()
        textField.translatesAutoresizingMaskIntoConstraints = false
        textField.returnKeyType = .done
        return textField
    }()
    
    weak var delegate: UITextFieldDelegate? {
        didSet {
            textField.delegate = delegate
        }
    }
    
    var onTextChanged: ((String) -> Void)?
    
    override init(style: UITableViewCell.CellStyle, reuseIdentifier: String?) {
        super.init(style: style, reuseIdentifier: reuseIdentifier)
        contentView.addSubview(textField)
        
        // Set constraints for the text field
        NSLayoutConstraint.activate([
            textField.leadingAnchor.constraint(equalTo: contentView.leadingAnchor, constant: 15),
            textField.trailingAnchor.constraint(equalTo: contentView.trailingAnchor, constant: -15),
            textField.topAnchor.constraint(equalTo: contentView.topAnchor),
            textField.bottomAnchor.constraint(equalTo: contentView.bottomAnchor)
        ])
        
        // Add editing changed listener
        textField.addTarget(self, action: #selector(textFieldDidChange), for: .editingChanged)
    }
    
    @objc private func textFieldDidChange() {
        onTextChanged?(textField.text ?? "")
    }
    
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }
}

class TasksViewController: UIViewController, UITableViewDataSource, UITableViewDelegate, UITextFieldDelegate, UITableViewDragDelegate {
    
    @IBOutlet weak var tasksTableView: UITableView!
    
    var tasks: [String] = [] // Data source for tasks
    var onExit: () -> Void = { }
    
    override func viewDidLoad() {
        super.viewDidLoad()
        
        tasks = (UserDefaults.standard.object(forKey: "tasks") as? [String])!

        // Register the custom cell
        tasksTableView.register(TaskCell.self, forCellReuseIdentifier: "TaskCell")
        tasksTableView.delegate = self
        tasksTableView.dataSource = self
        tasksTableView.dragDelegate = self
        tasksTableView.dragInteractionEnabled = true
        
        // Set a fixed row height
        tasksTableView.rowHeight = 40
        
        // Add observers for keyboard notifications
        NotificationCenter.default.addObserver(self, selector: #selector(keyboardWillShow(_:)), name: UIResponder.keyboardWillShowNotification, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(keyboardWillHide(_:)), name: UIResponder.keyboardWillHideNotification, object: nil)
    }

    @objc private func keyboardWillShow(_ notification: Notification) {
        if let keyboardFrame = notification.userInfo?[UIResponder.keyboardFrameEndUserInfoKey] as? CGRect {
            let keyboardHeight = keyboardFrame.height
            tasksTableView.contentInset = UIEdgeInsets(top: 0, left: 0, bottom: keyboardHeight, right: 0)
        }
    }

    @objc private func keyboardWillHide(_ notification: Notification) {
        tasksTableView.contentInset = .zero
    }

    func textFieldDidBeginEditing(_ textField: UITextField) {
        // Get the position of the text field in the table view
        let textFieldPosition = textField.convert(textField.bounds.origin, to: tasksTableView)
        if let indexPath = tasksTableView.indexPathForRow(at: textFieldPosition) {
            tasksTableView.scrollToRow(at: indexPath, at: .middle, animated: true)
        }
    }

    deinit {
        NotificationCenter.default.removeObserver(self, name: UIResponder.keyboardWillShowNotification, object: nil)
        NotificationCenter.default.removeObserver(self, name: UIResponder.keyboardWillHideNotification, object: nil)
    }
    
    // UITableViewDataSource Methods
    func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
        return tasks.count
    }
    
    func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        guard let cell = tableView.dequeueReusableCell(withIdentifier: "TaskCell", for: indexPath) as? TaskCell else {
            return UITableViewCell()
        }
        
        // Configure the cell
        cell.textField.text = tasks[indexPath.row]
        cell.selectionStyle = .none
        cell.delegate = self // Assign the view controller as the delegate
        cell.onTextChanged = { [weak self] text in
            self?.tasks[indexPath.row] = text
        }
        
        return cell
    }
    
    // Handle row deletion
    func tableView(_ tableView: UITableView, canEditRowAt indexPath: IndexPath) -> Bool {
        return true
    }
    
    func tableView(_ tableView: UITableView, commit editingStyle: UITableViewCell.EditingStyle, forRowAt indexPath: IndexPath) {
        if editingStyle == .delete {
            tasks.remove(at: indexPath.row) // Remove task
            tableView.deleteRows(at: [indexPath], with: .automatic)
            
            cleanTasksList()
            tableView.reloadData()
        }
    }
    
    @IBAction func addItemButton(_ sender: Any) {
        cleanTasksList()
        
        var index = 0
        while index < tasks.count {
            if tasks[index].trimmingCharacters(in: .whitespacesAndNewlines) == "" {
                tasks.remove(at: index)
            } else {
                index += 1
            }
        }
        
        addRow(task: "") // Add a new empty task
        
        // Get the cell for the last row and activate the text field
        let lastRowIndex = IndexPath(row: tasks.count - 1, section: 0)
        if let cell = tasksTableView.cellForRow(at: lastRowIndex) as? TaskCell {
            cell.textField.becomeFirstResponder()
        }
    }
    
    func addRow(task: String, atIndex: Int = -1) {
        var atIndex = atIndex
        if atIndex == -1 {
            atIndex = tasks.count
        }
        tasks.insert(task, at: atIndex)
        
        
        tasksTableView.reloadData()
        
        // Scroll to the last row
        let lastRowIndex = IndexPath(row: tasks.count - 1, section: 0)
        tasksTableView.scrollToRow(at: lastRowIndex, at: .bottom, animated: true)
    }
    
    // UITextFieldDelegate Methods
    func textFieldShouldReturn(_ textField: UITextField) -> Bool {
        textField.resignFirstResponder() // Dismiss the keyboard
        return true
    }
    
    @IBAction func backButtonPressed(_ sender: Any) {
        // cleanup tasks list
        var index = 0
        while index < tasks.count {
            if tasks[index].trimmingCharacters(in: .whitespacesAndNewlines) == "" {
                tasks.remove(at: index)
            } else {
                index += 1
            }
        }

        cleanTasksList()
        
        // handle case where there is just confirmation
        if tasks.count == 1 && tasks[0] == "CONFIRM" {
            tasks = []
        }
        
        UserDefaults.standard.set(tasks, forKey: "tasks")
        
        onExit()
        self.dismiss(animated: true)
    }
    
    @IBAction func addConfirmationButtonPress(_ sender: Any) {
        cleanTasksList()
        // find first index where confirmation can be inserted
        var index = 0
        while index < tasks.count {
            if index > 0 && tasks[index-1] == "CONFIRM" {
                // confirmation would come right before, which is bad
                index += 1
            } else if tasks[index] == "CONFIRM" {
                // confirmation would come right after, which is bad
                index += 1
            } else {
                break // since valid
            }
        }
        
        if tasks.count == 0 {
            index = 0
        }
        
        if index < tasks.count || tasks.count == 0 {
            // don't want to insert at very end
            addRow(task: "CONFIRM", atIndex: index)
        }
        
    }
    
    func tableView(_ tableView: UITableView, itemsForBeginning session: UIDragSession, at indexPath: IndexPath) -> [UIDragItem] {
        let dragItem = UIDragItem(itemProvider: NSItemProvider())
        dragItem.localObject = tasks[indexPath.row]
        return [ dragItem ]
    }
    
    func tableView(_ tableView: UITableView, moveRowAt sourceIndexPath: IndexPath, to destinationIndexPath: IndexPath) {
        // Update the model
        let mover = tasks.remove(at: sourceIndexPath.row)
        tasks.insert(mover, at: destinationIndexPath.row)
    }
    
    func cleanTasksList() {
        // Remove whitespace from all task names
        for index in 0..<tasks.count {
            tasks[index] = tasks[index].trimmingCharacters(in: .whitespacesAndNewlines)
        }
        
        var index = 0
        while index < tasks.count - 1 {
            if tasks[index] == "" {
                tasks.remove(at: index)
            } else {
                index += 1
            }
        }
        
        if tasks.count <= 1 {
            return
        }
        
        // can't have two confirmations in a row
        index = 0
        while index < tasks.count - 1 {
            if tasks[index] == "CONFIRM" && tasks[index+1] == "CONFIRM" {
                tasks.remove(at: index)
            } else {
                index += 1
            }
        }
        
        // confirmation can't be at end
        if tasks[tasks.count - 1] == "CONFIRM" {
            tasks.remove(at: tasks.count - 1)
        }
    }
    @IBAction func clearListButtonPressed(_ sender: Any) {
        // Clear the tasks array
        tasks = []
        
        // Save the empty array to UserDefaults
        UserDefaults.standard.set(tasks, forKey: "tasks")
        
        // Reload the table view to reflect the changes
        tasksTableView.reloadData()
    }
}
