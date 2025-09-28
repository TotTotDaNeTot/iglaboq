# from .minio_service import minio_service
# from werkzeug.utils import secure_filename

# import os



# def save_journal_images(journal_id, image_files):
#     """Сохраняет изображения в MinIO"""
#     saved_images = []
    
#     for i, image_file in enumerate(image_files):
#         if image_file and image_file.filename != '':
#             # Генерируем имя файла
#             file_extension = os.path.splitext(image_file.filename)[1].lower()
#             filename = f"{i + 1}{file_extension}"
            
#             # Загружаем в MinIO
#             image_url = minio_service.upload_image(journal_id, image_file, filename)
            
#             if image_url:
#                 saved_images.append({
#                     'filename': filename,
#                     'url': image_url
#                 })
    
#     return saved_images



# def delete_journal_image(journal_id, filename):
#     """Удаляет изображение из MinIO"""
#     return minio_service.delete_image(journal_id, filename)