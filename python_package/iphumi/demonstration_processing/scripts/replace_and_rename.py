import os
import json
import argparse

def replace_in_json_file(file_path, old_string, new_string):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        if old_string in content:
            content = content.replace(old_string, new_string)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Updated contents of: {file_path}")
    except Exception as e:
        print(f"Error processing {file_path}: {e}")

def rename_file_if_needed(file_path, old_string, new_string):
    dir_name = os.path.dirname(file_path)
    base_name = os.path.basename(file_path)
    if old_string in base_name:
        new_base_name = base_name.replace(old_string, new_string)
        new_path = os.path.join(dir_name, new_base_name)
        os.rename(file_path, new_path)
        print(f"Renamed file: {file_path} -> {new_path}")
        return new_path
    return file_path

def rename_directory_if_needed(dir_path, old_string, new_string):
    parent_dir = os.path.dirname(dir_path)
    dir_name = os.path.basename(dir_path)
    if old_string in dir_name:
        new_dir_name = dir_name.replace(old_string, new_string)
        new_path = os.path.join(parent_dir, new_dir_name)
        os.rename(dir_path, new_path)
        print(f"Renamed directory: {dir_path} -> {new_path}")
        return new_path
    return dir_path

def process_directory(root_dir, old_string, new_string):
    # First pass: bottom-up for renaming files and updating JSON content
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            updated_path = rename_file_if_needed(full_path, old_string, new_string)
            if updated_path.endswith(".json"):
                replace_in_json_file(updated_path, old_string, new_string)

    # Second pass: bottom-up renaming of directories
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
        for i in range(len(dirnames)):
            old_subdir = os.path.join(dirpath, dirnames[i])
            new_subdir = rename_directory_if_needed(old_subdir, old_string, new_string)
            # Update the dirnames list in-place so os.walk doesn't break
            dirnames[i] = os.path.basename(new_subdir)

    # Finally, rename the root dir itself if needed
    final_root = rename_directory_if_needed(root_dir, old_string, new_string)
    if final_root != root_dir:
        print(f"Root directory was renamed. New root: {final_root}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="""
Replace and Rename Script for Dataset Management

This script recursively processes a directory to:
1. Replace all occurrences of OLD_STRING with NEW_STRING in JSON file contents
2. Rename files that contain OLD_STRING in their names
3. Rename directories that contain OLD_STRING in their names

This is useful for:
- Updating dataset session names (e.g., changing "draw-O-0718" to "draw-T-0718")
- Batch renaming of demonstration files and directories
- Maintaining consistency across dataset files

Examples:
  # Update session name from 0718 to 0801
  python replace_and_rename.py /path/to/dataset --old "draw-O-0718" --new "draw-T-0718"
  
  # Update user name from "alice" to "bob"
  python replace_and_rename.py /path/to/dataset --old "alice" --new "bob"
  
  # Update task name
  python replace_and_rename.py /path/to/dataset --old "draw-circle" --new "draw-square"

Safety:
- The script processes files bottom-up to avoid path conflicts
- It handles both file contents and file/directory names
- JSON files are updated in-place
- All changes are logged to stdout
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("directory", help="Path to the directory to process")
    parser.add_argument("--old", required=True, help="String to replace (OLD_STRING)")
    parser.add_argument("--new", required=True, help="New string to use (NEW_STRING)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed without making changes")
    
    args = parser.parse_args()
    
    if not os.path.isdir(args.directory):
        print(f"Error: '{args.directory}' is not a valid directory.")
        exit(1)
    
    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")
        print(f"Would replace '{args.old}' with '{args.new}' in directory: {args.directory}")
        # TODO: Implement dry-run functionality
        exit(0)
    
    print(f"Processing directory: {args.directory}")
    print(f"Replacing '{args.old}' with '{args.new}'")
    print("Starting recursive replacement and renaming...")
    
    process_directory(os.path.abspath(args.directory), args.old, args.new)
    
    print("Processing complete!")