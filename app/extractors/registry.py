from app.extractors.catalogs import EmtopExtractor,IngcoExtractor,WurthExtractor
from app.extractors.generic import GenericExtractor
from app.extractors.mercadolibre import MercadoLibreExtractor
from app.extractors.goldfarb import GoldfarbExtractor
from app.extractors.orofino import OrofinoExtractor
from app.extractors.vicas import VicasExtractor
from app.extractors.ferreteradelnorte import FerreteraDelNorteExtractor
EXTRACTORS=[GoldfarbExtractor,OrofinoExtractor,VicasExtractor,FerreteraDelNorteExtractor,MercadoLibreExtractor,IngcoExtractor,EmtopExtractor,WurthExtractor,GenericExtractor]
def get_extractor(url,settings): return next(cls(settings) for cls in EXTRACTORS if cls.supports(url))
