"""
Defines search queries for keyword filtering research topics focused on
biodiversity dynamics in German regions including forest and habitat
environments, organized by dimension (Trends, Drivers, Conservation Measures,
Ecosystem Services) and categorized by Habitat (Forest, Soil, Agricultural/Open
Land, Inland Water, Coasts).

Provides Query dataclass instances with query texts associated with their
corresponding topic and habitat categories.

More information about the origin of the search queries can be found in
`./docs/SEARCH_QUERIES.md`.

```
...
class Habitat(Enum):
    "Habitats."

    FOREST = "Forest"
    SOIL = "Soil"
    AGRI = "Agricultural and Open Land"
    INLAND_WATER = "Inland waters & Floodplains"
    COAST = "Coasts & Coastal Waters"

class Topic(Enum):
    "Topics."

    TRENDS = "Trends"
    DRIVERS = "Drivers"
    MEASURES = "Measures"
    ECO_SERVICES = "Ecosystem Services"

@dataclass
class Query:
    id: str
    name: str
    query: str
    habitat: Habitat
    topic: Topic

ALL_SEARCH_QUERIES = [
    Query("Q1", "Forest - Trends", FOREST_TRENDS, Habitat.FOREST, Topic.TRENDS),
    Query("Q2", "Forest - Drivers", FOREST_DRIVERS, Habitat.FOREST, Topic.DRIVERS),
    Query("Q3", "Forest - Measures", FOREST_MEASURES, Habitat.FOREST, Topic.MEASURES),
    Query("Q4", "Forest - Ecosystem Services", FOREST_ECO_SERVICES, Habitat.FOREST, Topic.ECO_SERVICES),
    ...
    ]
```
"""

from dataclasses import dataclass
from enum import Enum

BIODIVERSITY = """("species richness" OR "species number*" OR "number of species" OR "species identity" OR "species composition" OR "species abundance" OR "species divers*" OR "species evenness" OR diversity OR "biodivers*" OR "biodiversity hotspot*" OR "genetic* divers*" OR "genetic* richness" OR "landscape divers*" OR "landscape structure" OR "landscape composition" OR "habitat divers*" OR "habitat structure" OR "habitat composition" OR "seascape structure" OR "structur* divers*" OR "community composition" OR "ecosystem* divers*" OR "ecosystem* structure" OR "ecosystem composition" OR "phylogenetic* divers*" OR "phylogenetic* richness" OR "number of taxa" OR "taxonomic* divers*" OR "taxonomic* richness" OR "functional* divers*" OR "functional* richness" OR "functional* composition" OR "functional* evenness" OR "functional* dissimilarity" OR "functional* similarity" OR shannon OR simpson OR evenness OR richness OR biomass OR abundance OR density OR "communit*")"""
GERMANY = """("German*" OR "central europ*" OR "Lower Saxony" OR Thuringia OR Saarland OR "Berlin*" OR "Brandenburg*" OR "Saxon*" OR "Saxony-Anhalt" OR "Bavar*" OR "Baden-Wuerttemberg" OR Bremen OR Hamburg OR "Hess*" OR "Mecklenburg-Western Pomerania" OR "North RhineWestphalia" OR "Rhineland-Palatinate" OR "Schleswig-Holstein")"""
FOREST_HABITAT = """("Forest*" OR "wood*" OR "stock of trees" OR stand OR stands OR "plantation*" OR "maple stand*" OR "birch stand*" OR "beech stand*" OR "rowan stand*" OR "yew stand*" OR "oak stand*" OR "alder stand*" OR "ash stand*" OR "spruce stand*" OR "hornbeam stand*" OR "hazel stand*" OR "chestnut stand*" OR "pine stand*" OR "larch stand*" OR "linden stand*" OR "poplar stand*" OR "sloe stand*" OR "fir stand*" OR "willow stand*" OR "hawthorne stand*" OR "elm stand*" OR deciduous OR coniferous OR "mixed forest*" OR "mixed woodland*" OR coppice OR copse)"""
BASE_KEYWORDS = BIODIVERSITY + " AND " + GERMANY + " AND " + FOREST_HABITAT
FOREST_TRENDS = (
    BASE_KEYWORDS
    + " AND "
    + """("trend*" OR "chang*" OR "decreas*" OR "gain*" OR "increas*" OR "los*" OR "loss*" OR "reduc*" OR "declin*" OR "extinct*" OR "develop*" OR "species loss" OR "biodiversity loss" OR "grow*" OR "endangered species" OR "extinct species")"""
)

FOREST_DRIVERS = (
    BASE_KEYWORDS
    + " AND "
    + """("habitat chang*" OR "habitat loss*" OR "habitat modification*" OR "habitatchang*" OR "habitat-loss*" OR "land use chang*" OR "landscape chang*" OR "land-use chang*" OR "deforest*" OR fragmentation OR "degrad*" OR "land-use intensification" OR afforestation OR "road construction" OR "urban pressure" OR "settlement pressure" OR "forest degradation" OR "extensive land*use" OR "litter use" OR "clearcut*" OR "wind throw*" OR "driv*" OR "pressur*" OR "stressor*" OR "biomass extract*" OR "raw material extract*" OR "resource extract*" OR wood OR timber OR lumber OR "hunt*" OR "poach*" OR "extract*" OR "overexploit*" OR "water extract*" OR "wood fuel*" OR "climate chang*" OR "climate warming" OR "extreme weather event*" OR "global warming" OR "global* chang*" OR "carbon dioxide" OR "GHG*" OR "greenhouse gas*" OR "*CO2" OR warming OR drought OR "weather extreme*" OR "heat wave*" OR "late frost" OR "heavy rain event*" OR "storm*" OR "flood event" OR flooding OR "contaminat*" OR "pollut*" OR "anthropogenic greenhouse effect" OR "heavy metal*" OR "toxi*" OR "nutrient content" OR "nutrient input" OR liming OR "pesticide*" OR "alien species" OR "introduced species" OR "invasi*" OR "non-native species" OR Bundeswaldgesetz OR Landeswaldgesetz OR Bundesnaturschutzgesetz OR BNatSchG OR Landesnaturschutzgesetz OR LNatSchG OR Klimaschutzgesetz OR FFH OR Natura2000 OR "Convention on Biological Diversity" OR CBD OR "Biodiversitätsstrategie*" OR "Waldstrategie*" OR "market*" OR "commodity trad*" OR "global demand" OR "urban forest owner*" OR "social change" OR "demography" OR awareness)"""
)
FOREST_MEASURES = (
    BASE_KEYWORDS
    + " AND "
    + """("protected area*" OR "national park*" OR "nature park*" OR "biosphere reserve*" OR "biotope*" OR "area conservation" OR "species conservation" OR "nature conservation" OR "landscape conservation" OR "habitat*" OR "priority area" OR sanctuary OR reserve OR "natural park*" OR "natural reserve*" OR "natural preserve*" OR "wildlife park *" OR "species protection" OR "protection of species" OR "nature protection" OR "landscape protection" OR conservation OR "close to nature" OR "near to nature" OR "process protection" OR "landscape conservation" OR "extensiv*" OR "maintenance measure*" OR monitoring OR "control*" OR "renatur*" OR "restor*" OR "regenerat*" OR "replacement measure*" OR "substitut* measure*" OR ecopoints OR "compensat* measure*" OR "land purchase" OR "parcel exchange" OR repopulation OR "reintroduc*" OR "environmental education" OR "raising awareness" OR certification OR landscaping OR "landscape maintenance" OR "alternative measures" OR "eco-points" OR "land acquisition" OR "remedial action*" OR "manag*" OR "conservation measure*")
"""
)
FOREST_ECOSYSTEM_SERVICES = (
    BASE_KEYWORDS
    + " AND "
    + """("carbon sequestration" OR " carbon cycling" OR "primary production" OR "carbon storage" OR "biomass production" OR "soil organic carbon" OR "decomposition" OR "dissolved organic carbon" OR "carbon leaching" OR "CO2 emission" OR "black carbon" OR "bioenergy production" OR "tillage" OR "harvest residues" OR "biofuel" OR "peat" OR "peat extraction" OR "peat decomposition" OR "methane emission" OR "paludiculture" OR "timber product*" OR "wood product*" OR "firewood" OR "deadwood" OR "coarse woody debris" OR "carbon sedimentation" OR "sediment retention" OR "energy production" OR "carbon emission" OR "carbon loss" OR "primary production" OR "fuelwood extraction" OR "bioeconomy" OR "fossil fuel substitution" OR "soil organic matter" OR "agroforestry" OR "soil erosion" OR "carbon burial" OR "climate regulation" OR "albedo" OR "cooling" OR "flood regulation" OR "flood protection" OR "water retention" OR "fire protection" OR "erosion protection" OR "resilience" OR "climate stability" OR "drought stability" OR "heat stability" OR "temperature stability" OR "climate resistance" OR "climate resilience" OR "buffering" OR "heat stress" OR "drought stress" OR "hotter drought" OR "droughtrelated mortality" OR "heat-related mortality" OR "radiation balance" OR "absorption" OR "heating" OR "climate mitigation" OR "shading" OR "transpiration" OR "evaporation" OR "desiccation" OR "latent heat production" OR "sensible heat production" OR "invasive pathogens" OR "invasive pests" OR "calamity" OR "frass" OR "fire" OR "ignition" OR "burning" OR "fire fuel" OR "combustion" OR "fire resistance" OR "fire damage" OR "flood" OR "flood attenuation" OR "flood retention" OR "anoxia" OR "flooding resistance" OR "flood defen?e" OR "wetlands" OR "flood storage" OR "flood generation" OR "flood detention" OR "flood event" OR "natural retention" OR "impacts of climate change" OR "recreation" OR "cultural" OR "spiritual" OR "intellectual" OR "cultural heritage" OR "learning" OR "inspiration" OR "physical experience" OR "psychological experience" OR "cultural service*" OR "ecotourism" OR "*aesthetic*" OR "education" OR "sport*" OR "hiking" OR "biking" OR "climbing" OR "sailing" OR "fishing" OR "hunting" OR "mental health" OR "religion" OR "perception" OR "valuation" OR "quality of life" OR "well-being" OR "extinction of experience" OR "preference*" OR "scenic beauty" OR "aesthetic" OR "tourism" OR "appreciation" OR "aesthetic value" OR "health" OR "relax*" OR fitness OR leisure OR "recov*" OR "rehab*" OR "artistic*" OR "entertain*" OR "enjoy*" OR "adventur*" OR "inspir*" OR "aware*")
"""
)
ECOSYSTEM_SERVICES_CROSS_SECTION = (
    BIODIVERSITY
    + " AND "
    + GERMANY
    + " AND "
    + """("carbon sequestration" OR "carbon cycling" OR "primary production" OR "carbon storage" OR "biomass production" OR "soil organic carbon" OR decomposition OR "dissolved organic carbon" OR "carbon leaching" OR "CO2 emission" OR "black carbon" OR "bioenergy production" OR tillage OR "harvest residues" OR biofuel OR peat OR "peat extraction" OR "peat decomposition" OR "methane emission" OR paludiculture OR "timber produc*" OR "wood product*" OR firewood OR deadwood OR "coarse woody debris" OR "carbon sedimentation" OR "sediment retention" OR "energy production" OR "carbon emission" OR "carbon loss" OR "primary production" OR "fuelwood extraction" OR bioeconomy OR "fossil fuel substitution" OR "soil organic matter" OR agroforestry OR "soil erosion" OR "carbon burial" OR "climate regulation" OR albedo OR cooling OR "flood regulation" OR "flood protection" OR "water retention" OR "fire protection" OR "erosion protection" OR resilience OR "climate stability" OR "drought stability" OR "heat stability" OR "temperature stability" OR "climate resistance" OR "climate resilience" OR buffering OR "heat stress" OR "drought stress" OR "hotter drought" OR "drought-related mortality" OR "heat-related mortality" OR "radiation balance" OR absorption OR heating OR "climate mitigation" OR shading OR transpiration OR evaporation OR desiccation OR "latent heat production" OR "sensible heat production" OR "invasive pathogens" OR "invasive pests" OR calamity OR frass OR fire OR ignition OR burning OR "fire fuel" OR combustion OR "fire resistance" OR "fire damage" OR flood OR "flood attenuation" OR "flood retention" OR anoxia OR "flooding resistance" OR "flood defen?e" OR wetlands OR "flood storage" OR "flood generation" OR "flood detention" OR "flood event" OR "natural retention" OR "impacts of climate change" OR recreation OR cultural OR spiritual OR intellectual OR "cultural heritage" OR learning OR "physical experience" OR "psychological experience" OR "cultural service*" OR ecotourism OR "*aesthetic*" OR education OR sports OR hiking OR biking OR climbing OR sailing OR fishing OR hunting OR "mental health" OR religion OR perception OR valuation OR "quality of life" OR "well-being" OR "extinction of experience" OR "preference*" OR "scenic beauty" OR tourism OR appreciation OR "aesthetic value" OR health OR "relax*" OR fitness OR leisure OR "recov*" OR "rehab*" OR "artistic*" OR "entertain*" OR "enjoy*" OR "adventur*" OR "inspir*" OR "aware*")"""
)
ECOSYSTEM_SERVICES_HABITATS = (
    BIODIVERSITY
    + " AND "
    + GERMANY
    + " AND "
    + ECOSYSTEM_SERVICES_CROSS_SECTION
    + " AND "
    + """("agricultur*" OR "open landscapes" OR "grassland*" OR "peatland*" OR "plain*" OR "field*" OR "farmland*" OR "Forest*" OR "wood*" OR "stock of trees" OR stand OR stands OR plantation OR "inland water*" OR "floodplain*" OR freshwater OR "river*" OR "lake*" OR "pond*" OR "stream*" OR groundwater OR "spring*" OR "wetland*" OR "inland wetland*" OR "peatland*" OR "bog*" OR "marsh*" OR "swamp*" OR "North Sea" OR "Helgoland" OR "Sylt" OR "Wadden Sea" OR "Weser" OR "Elbe" OR "Ems" OR "barrier island" OR "frisian island*" OR "German Bight" OR baltic OR "Kiel fjord" OR "Flensborg fjord" OR "urban*" OR "metropol*" OR city OR cities OR capital OR "municipal*" OR town OR settlement OR "built-up area*" OR "artificial* area*" OR "sealed area*" OR impervious OR suburban OR "peri-urban" OR anthropogenic OR neighbourhood OR "building*" OR "brownfield*" OR ruderal OR remnant OR "Central Business District")"""
)
SOIL_HABITAT = """(soil OR "soil-dwelling" OR "below$ground" OR "below-ground") AND (biota OR fauna OR "micro$fauna" OR" micro-fauna" OR "meso$fauna" OR "meso-fauna" OR "macro$fauna" OR macrofauna OR "mega$fauna" OR "mega-fauna" OR "protozoa*" OR "bacteria*" OR "proteobacteria*" OR "cyanobacteria*" OR "actinobacteria*" OR firmicutes OR archaea OR euryarchaeota OR crenarchaeota OR thaumarchaeota OR "protist*" OR rhizaria OR "ameb*" OR "amoeb*" OR "alveolat*" OR "stramenopile*" OR excavata OR "fung*" OR "ascomyc*" OR "basidiomyc*" OR "glomeromyc*" OR "zygomyc*" OR "chytridiomyc*" OR "blastocladiomyc*" OR "microb*" OR "animal*" OR "rotifer*" OR "nematod*" OR "mollusc*" OR "gastropod*" OR "snail*" OR "slug*" OR "annelid*" OR "oligochaet*" OR "earthworm*" OR "lumbricid*" OR "enchytrae*" OR "clitellat*" OR "haplotaxid*" OR "tardigrad*" OR "arthropod*" OR "micro$arthropod*" OR "micro-arthropod*" OR "macro$arthropod*" OR "macro-arthropod*" OR "chelicerat*" OR "arachnid*" OR acari OR "mite*" OR araneae OR "spider*" OR "pseudoscorpion*" OR "scorpion*" OR "myriapod*" OR "chilopod*" OR "centiped*" OR "diplopod*" OR "milliped*" OR "pauropod*" OR "symphyla*" OR "crustacea*" OR "malacostraca*" OR "isopod*" OR lice OR "hexapod*" OR "entognath*" OR "collembol*" OR "springtail*" OR "protura*" OR "diplura*" OR "insect*" OR "hymenopter*" OR "sawfl*" OR "wasp*" OR "ant*" OR "isopter*" OR "termite*" OR "coleopter*" OR "beetle*" OR "dipter*" OR fly OR flies OR "hemipter*" OR "cicada*" OR "aphid*" OR "planthopper*" OR "leafhopper*" OR "bug*" OR "lepidopter*" OR "butterfly*" OR "moth*" OR "neuropter*" OR "lacewing*" OR "mantidfl*" OR "antlion*" OR "inverte*" OR "chordat*" OR "vertebrat*" OR "amphibia*" OR "frog*" OR "toad*" OR "salamander*" OR "newt*" OR "reptil*" OR "mammal*" OR "hamster*" OR "mole*" OR "soil biodiversity" OR "below$ground biodiversity" OR "soil divers*" OR "below$ground divers*")"""

SOIL_TRENDS = (
    BIODIVERSITY
    + " AND "
    + GERMANY
    + " AND "
    + SOIL_HABITAT
    + " AND "
    + """("trend*" OR "chang*" OR "decreas*" OR "gain*" OR "increas*" OR "los*" OR "reduc*" OR "declin*" OR "extinct*" OR "species loss" OR "biodiversity loss" OR "grow*" OR endangered OR "develop*" OR extinct)"""
)

SOIL_DRIVERS = (
    BIODIVERSITY
    + " AND "
    + GERMANY
    + " AND "
    + SOIL_HABITAT
    + " AND "
    + """("driv*" OR "pressur*" OR "stressor*" OR "contami*" OR "pollut*" OR "antropogen* greenhouse effect" OR "heavy metal*" OR "toxi*" OR pesticide OR insecticide OR "chemical*" OR "herbicide*" OR "plant protection products" OR "habitat$chang*" OR "habitat$loss*" OR "habitat$modification*" OR "land$use change*" OR "land$use intensification" OR "biomass extract*" OR "raw material extract*" OR "resource extract*" OR "overexploit*" OR "landscape$change*" OR "use of space" OR "space utili*" OR "land utili*" OR zoning OR "land managment" OR fragmentation OR "degrad*" OR "soil compaction" OR "area sealing" OR "land sealing" OR "surface sealing" OR "sealing of ares" OR downgrading OR compression OR compaction OR erosion OR eroding OR "climate$chang*" OR "climate warming" OR "extrem weather event*" OR "global warming" OR "global* chang*" OR "greenhouse gas*" OR GHG OR "carbon dioxide" OR CO2 OR "alien species" OR "exotic species" OR "introduc* species" OR "invasi*" OR "invasiv* species" OR "non$native species" OR waste OR "soil drainage" OR "surface water managment" OR "light pollut*")"""
)
SOIL_MEASURES = (
    BIODIVERSITY
    + " AND "
    + GERMANY
    + " AND "
    + SOIL_HABITAT
    + " AND "
    + """("protected area" OR "national park*" OR "natur* park*" OR "biosphere reserve*" OR "biotope*" OR "area conservation" OR "species conservation" OR "nature conservation" OR "landscape conservation" OR "habitat conservation" OR "priority area*" OR "sanctuar*" OR reserve OR "natur* reserv*" OR "wild* park" OR "natural preserve" OR "species protection" OR "protection of species" OR "nature protection" OR "landscape protection" OR conservation OR "maintenanc*" OR "monitor*" OR "control*" OR "renatur*" OR "restor*" OR "regenerat*" OR "replacement measures" OR "subsitut* measures" OR "eco$points" OR "compensat*" OR "land purchase" OR "parcel exchange" OR repopulation OR "reintroduc*" OR "environmental education" OR "raising awareness" OR certification OR "alternative measure*" OR "land acquisition" OR "remedi* action" OR "conservation measure*" OR "ecologic* improvement" OR "ecologic* enhancement" OR "ecologic* upgrading" OR "ecologic* optimisation" OR "enviromental optimisition" OR rehabilitation OR remediation OR acceptance OR "assessment basis" OR "impact assessment" OR target OR "quality control" OR "environmental* compatible" OR "eco$friendly" OR "nature compatible" OR "near$natur*" OR "protect*" OR "restaur*" OR "preserv*" OR "repopulat*" OR "rewild*" OR "landscape plan*" OR "manage*" OR "extensiv*" OR "remedi* measure*" OR "landscape reserv*" OR "protected landscape*" OR "Natura2000 site*" OR "biodiversity reserv*")"""
)

SOIL_ECOSYSTEM_SERVICES = (
    BIODIVERSITY
    + " AND "
    + GERMANY
    + " AND "
    + SOIL_HABITAT
    + " AND "
    + """("ecosystem service*" OR "ecosystem function*" OR "contribution to people" OR "ecosystem health" OR "ecosystem properties" OR disservice OR "Provisioning service*" OR food OR water OR "*energy" OR "wood*" OR "raw material" OR "medicinal resource*" OR biomass OR yield OR "genetic material" OR "disease resistance" OR nutrition OR "regulating service*" OR "carbon cycling" OR "water retention" OR "air purification" OR "water purification" OR "climate regulation" OR "soil fertility" OR "flood regulation" OR "erosion protection" OR "disease control" OR "pest control" OR "fire protection" OR "wind protection" OR "noise reduction" OR "odo*r reduction" OR "carbon sequestration" OR "waste decomposition" OR detoxification OR "flood protection" OR cooling OR "wood production" OR albedo OR "invasion resistance" OR "water quality" OR "air quality " OR Resilience OR Stability OR "Nutrient* retention" OR "Nutrient* translocation" OR "Natural pest control" OR "Biological control" OR "Biological pest control" OR "erosion protection" OR "pollinat*" OR "sustainab*" OR "cultural service*" OR recreation OR "cultural heritage" OR ecotourism OR aesthetic OR spiritual OR cultural OR intellectual OR learning OR inspiration OR "physical experiences" OR "psychological experiences" OR "supporting service*" OR "soil formation" OR "Nutrient Cycling" OR pollination OR "primary production" OR "nitrogen fixation" OR "seed dispersal" OR "habitat creation" OR "habitat maintenance" OR "Soil stability" OR "carbon sequestration" OR "carbon cycling" OR "primary production" OR "carbon storage" OR "biomass production" OR "soil organic carbon" OR decomposition OR "dissolved organic carbon" OR "carbon leaching" OR "CO2 emission" OR "black carbon" OR "bioenergy production" OR tillage OR "harvest residues" OR biofuel OR peat OR "peat extraction" OR "peat decomposition" OR "methane emission" OR paludiculture OR "timber produc*" OR "wood product*" OR firewood OR deadwood OR "coarse woody debris" OR "carbon sedimentation" OR "sediment retention" OR "energy production" OR "carbon emission" OR "carbon loss" OR "primary production" OR "fuelwood extraction" OR bioeconomy OR "fossil fuel substitution" OR "soil organic matter" OR agroforestry OR "soil erosion" OR "carbon burial" OR "climate regulation" OR albedo OR cooling OR "flood regulation" OR "flood protection" OR "water retention" OR "fire protection" OR "erosion protection" OR resilience OR "climate stability" OR "drought stability" OR "heat stability" OR "temperature stability" OR "climate resistance" OR "climate resilience" OR buffering OR "heat stress" OR "drought stress")"""
)
HABITATS_AGRICULTURAL = """("agricultur*" OR "open landscapes" OR "grassland*" OR "peatland*" OR "plain*" OR "field*" OR "farmland*")"""
HABITATS_WATER = """("inland water*" OR "floodplain*" OR freshwater OR "river*" OR "lake*" OR "pond*" OR "stream*" OR groundwater OR "spring*" OR "wetland*" OR "inland wetland*" OR "peatland*" OR "bog*" OR "marsh*" OR "swamp*")"""
HABITATS_COASTS = """("North Sea" OR "Helgoland" OR "Sylt" OR "Wadden Sea" OR "Weser" OR "Elbe" OR "Ems" OR "frisian island*" OR Arkona OR "German Bight" OR baltic OR "Kiel fjord" OR "Flensborg fjord" OR "German coast")"""
HABITATS_URBAN = """("urban*" OR "metropol*" OR city OR cities OR capital OR "municipal*" OR town OR settlement OR "built-up area*" OR "artificial* area*" OR "sealed area*" OR impervious OR suburban OR "peri-urban" OR anthropogenic OR neighbourhood OR "building*" OR "brownfield*" OR ruderal OR remnant OR "Central Business District")"""

TRENDS = (
    HABITATS_AGRICULTURAL
    + " AND "
    + """("endangered species" OR "extinct species")"""
    + " AND "
    + """("trend*" OR "chang*" OR "decreas*" OR "gain*" OR "increas*" OR "los*" OR "reduc*" OR "declin*" OR "extinct*" OR "species loss" OR "biodiversity loss" OR "grow*" OR endangered) """
)

DRIVERS = """("habitat chang*" OR "habitat loss*" OR "habitat modification*" OR "habitat-chang*" OR "habitat-loss*" OR "land use chang*" OR "landscape chang*" OR "land-use chang*" OR fragmentation OR "degrad*" OR "land* intensification" OR intensification OR "extensive land*use" OR extensification OR "driv*" OR "pressur*" OR "stressor*" OR "agricultur* expansion" OR "crop* expansion" OR "graz* expansion" OR livestock OR "animal husbandry" OR "herd*" OR "grassland abandonment" OR drainage OR "biomass extract*" OR "raw material extract*" OR "resource extract*" OR "extract*" OR "overexploit*" OR "crop rotation" OR "crop reduction" OR "peat degradation" OR "hummus degradation" OR "climate chang*" OR "climate warming" OR "extreme weather event*" OR "global warming" OR "global* chang*" OR "carbon dioxide" OR "GHG*" OR "greenhouse gas*" OR "*CO2" OR warming OR drought OR "weather extreme*" OR "heat wave*" OR "late frost" OR "heavy rain event*" OR "storm*" OR "flood event" OR flooding OR precipitation OR "contaminat*" OR "contaminant*" OR "pollut*" OR "anthropogenic greenhouse effect" OR "heavy metal*" OR "toxi*" OR "nutrient content" OR "nutrient input" OR liming OR "pesticide*" OR "fertiliz*" OR "soil acidification" or "light pollut*" OR "alien species" OR "introduced species" OR "invasi*" OR "non-native species" OR "introduced predator*" OR "introduced parasite*" OR "introduced disease*" OR "homogeniz* land*" OR "urban pressure" OR "settlement pressure" OR "road construction" OR "landscape elements" OR fallow OR irrigation OR "marginal crop*" OR "windmill*" OR "market*" OR "commodity trad*" OR "global demand" OR "energy regime" OR "techn* progress" OR "agricultural specialization" OR Bundesnaturschutzgesetz OR BNatSchG OR Landesnaturschutzgesetz OR LNatSchG OR Klimaschutzgesetz OR FFH OR Natura2000 OR "Convention on Biological Diversity" OR CBD OR "Biodiversitätsstrategie*" OR "agricultural policy" OR "land*use policy" or "nature conservation" OR policy OR "green band" OR "Flächen*stillegung*" OR "renewable energy policy" OR "social change" OR awareness OR leisure OR "loss of knowledge" OR "loss of awareness" OR media OR "distanc* consumer* product*" OR "land consolidation" OR "society engagement" OR "citizen science" OR "citizen initiative" OR NGO)"""

METRICS = """(conservation OR "protect*" OR "restaur*" OR "renatur*" OR "preserv*" OR "monitor*" OR "restor*" OR "regenerat*" OR "repopulat*" OR "rewild*" OR "reintroduc*" OR "landscape plan*" OR "manage*" OR "extensiv*" OR "conservation* measure*" OR "maintenanc*" OR "compensat*" OR "remedi* action*" OR "remedi* measure*" OR "national park*" OR "nature park*" OR "biotope*" OR "priority area*" OR sanctuary OR sanctuaries OR "nature reserv*" OR "natural reserv*" OR "landscape reserv*" OR "protected landscape*" OR "natural park*" OR "wildlife park*" OR "biosphere reserv*" OR "Natura2000 site*" OR "bird reserv*" OR "protected area*" OR "conservation area*" OR "biodiversity reserv*")"""


class Habitat(Enum):
    """Habitats."""

    FOREST = "Forest"
    SOIL = "Soil"
    AGRI = "Agricultural and Open Land"
    INLAND_WATER = "Inland waters & Floodplains"
    COAST = "Coasts & Coastal Waters"


class Topic(Enum):
    """Topics."""

    TRENDS = "Trends"
    DRIVERS = "Drivers"
    MEASURES = "Measures"
    ECO_SERVICES = "Ecosystem Services"


@dataclass
class Query:
    id: str
    name: str
    query: str
    habitat: Habitat
    topic: Topic


ALL_SEARCH_QUERIES = [
    Query("Q1", "Forest - Trends", FOREST_TRENDS, Habitat.FOREST, Topic.TRENDS),
    Query("Q2", "Forest - Drivers", FOREST_DRIVERS, Habitat.FOREST, Topic.DRIVERS),
    Query("Q3", "Forest - Measures", FOREST_MEASURES, Habitat.FOREST, Topic.MEASURES),
    Query(
        "Q4",
        "Forest - Ecosystem Services",
        FOREST_ECOSYSTEM_SERVICES,
        Habitat.FOREST,
        Topic.ECO_SERVICES,
    ),
]
