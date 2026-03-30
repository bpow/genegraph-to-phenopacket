# src/config.py

# Resource Metadata for Phenopackets
RESOURCE_METADATA = [
    {
        "id": "hp",
        "name": "Human Phenotype Ontology",
        "url": "http://purl.obolibrary.org/obo/hp.owl",
        "namespace_prefix": "HP"
    },
    {
        "id": "mondo",
        "name": "Mondo Disease Ontology",
        "url": "http://purl.obolibrary.org/obo/mondo.owl",
        "namespace_prefix": "MONDO"
    },
    {
        "id": "geno",
        "name": "Genotype Ontology",
        "url": "http://purl.obolibrary.org/obo/geno.owl",
        "namespace_prefix": "GENO"
    },
    {
        "id": "eco",
        "name": "Evidence and Conclusion Ontology",
        "url": "https://evidenceontology.org/repo/ECO.owl",
        "namespace_prefix": "ECO"
    }
]

FALLBACK_DISEASE_ID = "MONDO:0700096"
FALLBACK_DISEASE_LABEL = "human disease"