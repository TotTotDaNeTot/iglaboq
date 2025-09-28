from minio import Minio



minio_client = Minio(
    "wholly-active-butterfish.cloudpub.ru",
    access_key="myuser",
    secret_key="mypassword123", 
    secure=True
)