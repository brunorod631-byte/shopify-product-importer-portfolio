import io
from dataclasses import dataclass
import imagehash
from PIL import Image,ImageOps,UnidentifiedImageError
@dataclass
class ProcessedImage: content:bytes; extension:str; perceptual_hash:str
def process_image(content:bytes,min_side:int=250):
    try:
        with Image.open(io.BytesIO(content)) as src: src.verify()
        with Image.open(io.BytesIO(content)) as src:
            image=ImageOps.exif_transpose(src)
            if min(image.size)<min_side or image.width*image.height>50_000_000:return None
            digest=str(imagehash.phash(image)); output=io.BytesIO(); image.convert("RGB").save(output,"JPEG",quality=90,optimize=True)
            return ProcessedImage(output.getvalue(),".jpg",digest)
    except (UnidentifiedImageError,OSError,ValueError): return None
def deduplicate(images):
    seen=set(); return [x for x in images if not (x.perceptual_hash in seen or seen.add(x.perceptual_hash))]
