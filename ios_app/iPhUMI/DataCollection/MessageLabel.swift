/*
See LICENSE folder for this sample’s licensing information.

Abstract:
A label to present the user with feedback.
*/

import UIKit

@IBDesignable
class MessageLabel: UITextView {
    
    var ignoreMessages = false
		
//	override func drawText(in rect: CGRect) {
//		let insets = UIEdgeInsets(top: 0, left: 5, bottom: 0, right: 5)
//		super.drawText(in: rect.inset(by: insets))
//	}
    
    func displayMessage(_ text: String) {
        guard !ignoreMessages else { return }
        guard !text.isEmpty else {
            DispatchQueue.main.async {
                self.isHidden = true
                self.text = ""
            }
            return
        }
        
        print(text)
        
        DispatchQueue.main.async {
            self.isHidden = false
            
            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "hh:mm:ss"
            let date = dateFormatter.string(from: Date())
            
            self.text = self.text! + (self.text == "" ? "" : "\n") + date + " " + text
            
            // Use a tag to tell if the label has been updated.
            let tag = self.tag + 1
            self.tag = tag
            
            let bottom = NSMakeRange(self.text.count - 1, 1)
            self.scrollRangeToVisible(bottom)
            
//            DispatchQueue.main.asyncAfter(deadline: .now() + duration) {
//                // Do not hide if this method is called again before this block kicks in.
//                if self.tag == tag {
//                    self.isHidden = true
//                }
//            }
        }
    }
}
