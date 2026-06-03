$ErrorActionPreference = "Stop"

$ProjectId = "moran-cce72"
$Region = "europe-west1"
$Repo = "moran-jobs"
$JobName = "moran-daily-job-scan"
$SchedulerName = "moran-daily-job-scan-evening"
$RuntimeServiceAccount = "firebase-adminsdk-fbsvc@$ProjectId.iam.gserviceaccount.com"
$Image = "$Region-docker.pkg.dev/$ProjectId/$Repo/$JobName`:latest"
$RtdbUrl = "https://moran-cce72-default-rtdb.europe-west1.firebasedatabase.app"

gcloud config set project $ProjectId
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

$repoExists = $false
try {
  gcloud artifacts repositories describe $Repo --location $Region --project $ProjectId | Out-Null
  $repoExists = $true
} catch {
  $repoExists = $false
}
if (-not $repoExists) {
  gcloud artifacts repositories create $Repo --repository-format=docker --location=$Region --description="Moran job scanner images" --project $ProjectId
}

gcloud builds submit --tag $Image --project $ProjectId .

gcloud run jobs deploy $JobName `
  --image $Image `
  --region $Region `
  --project $ProjectId `
  --service-account $RuntimeServiceAccount `
  --tasks 1 `
  --max-retries 1 `
  --task-timeout 3600 `
  --set-env-vars "FIREBASE_RTDB_URL=$RtdbUrl"

gcloud run jobs add-iam-policy-binding $JobName `
  --region $Region `
  --project $ProjectId `
  --member "serviceAccount:$RuntimeServiceAccount" `
  --role roles/run.invoker

$Uri = "https://run.googleapis.com/v2/projects/$ProjectId/locations/$Region/jobs/$JobName`:run"
$schedulerExists = $false
try {
  gcloud scheduler jobs describe $SchedulerName --location $Region --project $ProjectId | Out-Null
  $schedulerExists = $true
} catch {
  $schedulerExists = $false
}

if ($schedulerExists) {
  gcloud scheduler jobs update http $SchedulerName `
    --location $Region `
    --project $ProjectId `
    --schedule "0 20 * * *" `
    --time-zone "Asia/Jerusalem" `
    --uri $Uri `
    --http-method POST `
    --oauth-service-account-email $RuntimeServiceAccount
} else {
  gcloud scheduler jobs create http $SchedulerName `
    --location $Region `
    --project $ProjectId `
    --schedule "0 20 * * *" `
    --time-zone "Asia/Jerusalem" `
    --uri $Uri `
    --http-method POST `
    --oauth-service-account-email $RuntimeServiceAccount
}

gcloud run jobs execute $JobName --region $Region --project $ProjectId --wait
