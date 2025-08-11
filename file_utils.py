import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf', 'doc', 'docx'}

def allowed_file(filename):
    """Check if the file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_file(file, document_type, user_id):
    """
    Save uploaded file with a secure filename
    
    Args:
        file: The uploaded file object
        document_type: Type of document (e.g., 'national_id', 'provisional_license')
        user_id: The user's ID for organizing files
    
    Returns:
        str: The relative path to the saved file, or None if error
    """
    if file and allowed_file(file.filename):
        # Generate a secure filename
        filename = secure_filename(file.filename)
        # Add UUID to prevent filename conflicts
        name, ext = os.path.splitext(filename)
        unique_filename = f"{user_id}_{document_type}_{uuid.uuid4().hex[:8]}{ext}"
        
        # Create user directory if it doesn't exist
        user_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        
        # Save the file
        file_path = os.path.join(user_dir, unique_filename)
        file.save(file_path)
        
        # Return relative path for database storage
        return os.path.join('uploads', str(user_id), unique_filename)
    
    return None

def delete_file(file_path):
    """Delete a file from the uploads directory"""
    if file_path:
        full_path = os.path.join('static', file_path)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
                return True
            except OSError:
                pass
    return False

def get_file_size_mb(file):
    """Get file size in MB"""
    if file:
        file.seek(0, os.SEEK_END)
        size = file.tell()
        file.seek(0)  # Reset file pointer
        return size / (1024 * 1024)  # Convert to MB
    return 0