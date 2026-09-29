# Google Cloud

The jury demo runs on one Compute Engine VM (e2-standard-4, europe-north1) with the same Docker Compose
as the local demo, plus `compose.gcp.yaml`: the site listens on port 80 and opens through a secret link.

1. Create the VM with a static IP and open port 80:

       gcloud compute addresses create sitewatch-ip --region europe-north1
       gcloud compute firewall-rules create sitewatch-http --allow tcp:80 --target-tags sitewatch
       gcloud compute instances create sitewatch --zone europe-north1-a --machine-type e2-standard-4 \
         --image-family debian-12 --image-project debian-cloud --boot-disk-size 50GB \
         --tags sitewatch --address sitewatch-ip

2. Copy the repository, `models/sitewatch-v2/` and `deploy/gcp/.env` to the VM. The env file is not in git:

       DESCRIBE_API_URL=…
       DESCRIBE_API_KEY=…
       DESCRIBE_MODEL=…
       SITEWATCH_INTERNAL_TOKEN=<openssl rand -hex 32>
       SITEWATCH_SHARE_TOKEN=<openssl rand -hex 32>
       SITEWATCH_ORIGIN=http://<static IP>

3. On the VM run `deploy/gcp/vm-up.sh`, then `deploy/gcp/prewarm.sh` once: it runs every demo frame through
   both recognition modes, and the results are kept in the `inference-cache` volume across restarts.
   The link for the jury is
   `http://<static IP>/app/model?access=<SITEWATCH_SHARE_TOKEN>`; one visit keeps access for 14 days.
