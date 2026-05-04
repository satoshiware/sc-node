git status
git add -A
git commit -m "Updating fixes to reward endpoint to improve time turnaround. 0.2.0"
git tag v0.2.0  
git push origin main
git push origin v0.2.0

$ErrorActionPreference = "Stop"

$IMAGE = "ghcr.io/satoshiware/sc-node/master-api"
$VERSION = "v0.2.0"
$SHA = (git rev-parse --short HEAD).Trim()

docker build `
  -t "${IMAGE}:latest" `
  -t "${IMAGE}:${VERSION}" `
  -t "${IMAGE}:sha-${SHA}" `
  .

docker push "${IMAGE}:latest"
docker push "${IMAGE}:${VERSION}"
docker push "${IMAGE}:stable"
docker push "${IMAGE}:sha-${SHA}"