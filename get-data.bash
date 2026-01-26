DATE=$(date +'%Y%m%d')
mkdir input/gene-validity-$DATE
curl https://storage.googleapis.com/genegraph-public/gene-validity-jsonld-latest.tar.gz \
	| tar -C input/gene-validity-$DATE +'%Y%m%d') -xvf -
