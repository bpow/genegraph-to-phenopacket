DATE=$(date +'%Y%m%d')
mkdir -p data/input/gene-validity-$DATE
curl https://storage.googleapis.com/genegraph-public/gene-validity-jsonld-latest.tar.gz \
	| tar -C data/input/gene-validity-$DATE -xzvf -
