"""FAQ uploads have no public URLs. The guide endpoint enforces audience on every read."""

from django.conf import settings
from django.core.files.storage import FileSystemStorage

from botocore.exceptions import ClientError
from storages.backends.s3 import S3Storage
from storages.utils import clean_name


class PrivateGuideFiles(FileSystemStorage):
    def url(self, name):
        raise ValueError("FAQ faylına yalnız təlimatın keçidi ilə baxılır.")


class PrivateGuideObjects(S3Storage):
    def url(self, name, **kwargs):
        raise ValueError("FAQ faylına yalnız təlimatın keçidi ilə baxılır.")

    def open_range(self, name, byte_range):
        key = self._normalize_name(clean_name(name))
        options = {"Range": byte_range} if byte_range else {}
        try:
            return self.bucket.Object(key).get(**options)["Body"]
        except ClientError as error:
            if error.response["ResponseMetadata"]["HTTPStatusCode"] == 404:
                raise FileNotFoundError(name) from error
            raise


def faq_upload_storage():
    # A private named bucket is opt-in. The production media volume is shared by
    # web replicas even on installations using an object store for other media.
    bucket = getattr(settings, "FAQ_PRIVATE_S3_BUCKET", "")
    if bucket:
        return PrivateGuideObjects(
            bucket_name=bucket,
            custom_domain=None,
            default_acl=None,
            object_parameters={"CacheControl": "private, no-store"},
        )
    return PrivateGuideFiles()
