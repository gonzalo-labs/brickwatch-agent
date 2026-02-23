import json

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_cloudfront as cf
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3d
from aws_cdk import custom_resources as cr
from constructs import Construct


class UiHostingStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        api_url: str,
        api_key_value: str,
        cognito_domain: str,
        user_pool_client_id: str,
        user_pool_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        normalized_api_url = api_url.rstrip("/")

        site_bucket = s3.Bucket(
            self,
            "BrickwatchWebBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        oai = cf.OriginAccessIdentity(self, "BrickwatchOAI")

        dist = cf.Distribution(
            self,
            "BrickwatchDist",
            default_root_object="index.html",
            default_behavior=cf.BehaviorOptions(
                origin=origins.S3Origin(site_bucket, origin_access_identity=oai),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
        )

        site_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject"],
                resources=[site_bucket.arn_for_objects("*")],
                principals=[
                    iam.CanonicalUserPrincipal(
                        oai.cloud_front_origin_access_identity_s3_canonical_user_id # type: ignore[arg-type]
                    )
                ],  
            )
        )

        html_template = """<!doctype html><html><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" /><title>Brickwatch</title>
<link rel=\"icon\" href=\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Ccircle cx='32' cy='32' r='28' fill='%2322c55e'/%3E%3Ctext x='32' y='39' font-size='28' text-anchor='middle' fill='%2309210f' font-family='Arial'%3ES%3C/text%3E%3C/svg%3E\"/>
<style>
  :root{--bg:#0f172a;--card:#0b1220;--muted:#94a3b8;--accent:#22c55e;--text:#e5e7eb}
  *{box-sizing:border-box} body{margin:0;background:linear-gradient(180deg,#0b1220,#0f172a);font:16px system-ui;color:var(--text)}
  .container{max-width:900px;margin:40px auto;padding:0 20px}
  .hero{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
  .brand{font-weight:700;font-size:22px;letter-spacing:.3px}
  .card{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:16px}
  .row{display:flex;gap:12px;flex-wrap:wrap}
  textarea{width:100%;min-height:96px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:#0b1220;color:var(--text);padding:10px}
  button{background:var(--accent);color:#09210f;border:0;border-radius:10px;padding:10px 14px;font-weight:600;cursor:pointer}
  button.link{background:transparent;color:var(--text);border:1px solid rgba(255,255,255,.15)}
  .muted{color:var(--muted)}
  #log{white-space:pre-wrap;background:#0b1220;border:1px solid rgba(255,255,255,.1);border-radius:12px;padding:12px;min-height:120px}
  .pill{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.12);padding:6px 10px;border-radius:999px;font-size:12px}
  .spacer{height:12px}
  hr{border:none;border-top:1px solid rgba(255,255,255,.08);margin:20px 0}
</style>
</head><body><div class=\"container\">
  <div class=\"hero\">
    <div class=\"brand\">Brickwatch</div>
    <div>
      <button id=\"signin\" class=\"link\">Sign in with Cognito</button>
      <button id=\"signout\" class=\"link\" style=\"display:none\">Sign out</button>
    </div>
  </div>
  <div class=\"muted\" id=\"who\">Not signed in</div>
  <div class=\"spacer\"></div>
  <div class=\"card\">
    <div class=\"muted\" style=\"margin-bottom:8px\">Ask Brickwatch</div>
    <textarea id=\"goal\" placeholder=\"Find cost anomalies this week and propose fixes...\"></textarea>
    <div class=\"row\" style=\"margin-top:10px\">
      <button id=\"send\">Send</button>
      <div class=\"pill\">API key + Cognito auth</div>
    </div>
  </div>
  <div class=\"spacer\"></div>
  <div class=\"card\">
    <div class=\"muted\" style=\"margin-bottom:8px\">Response</div>
    <div id=\"log\"></div>
  </div>
</div>
  <script>
  var apiUrl = __API_URL__;
  if (apiUrl && apiUrl.charAt(apiUrl.length-1) === '/') { apiUrl = apiUrl.slice(0, -1); }
  var cognitoDomain = __COGNITO_DOMAIN__;
  var clientId = __CLIENT_ID__;
  var redirectUri = window.location.origin + '/';

  function parseHash(){
    try{
      if(window.location.hash && window.location.hash.indexOf('#') === 0){
        var p=new URLSearchParams(window.location.hash.substring(1));
        var id=p.get('id_token');
        var acc=p.get('access_token');
        if(id){ localStorage.setItem('id_token',id); }
        if(acc){ localStorage.setItem('access_token',acc); }
        if(id||acc){ history.replaceState({},document.title,window.location.pathname); }
      }
    }catch(e){ console.error('parseHash',e); }
  }
  parseHash();

  function updateUi(){
    var t=localStorage.getItem('id_token');
    var signin=document.getElementById('signin');
    var signout=document.getElementById('signout');
    var who=document.getElementById('who');
    if(signin) signin.style.display = t ? 'none' : '';
    if(signout) signout.style.display = t ? '' : 'none';
    if(who) who.textContent = t ? 'Signed in' : 'Not signed in';
  }
  updateUi();

  document.getElementById('signin').onclick = function(){
    var url = 'https://' + cognitoDomain + '/login?response_type=token&client_id=' + encodeURIComponent(clientId) + '&redirect_uri=' + encodeURIComponent(redirectUri) + '&scope=openid+email+profile';
    window.location.assign(url);
  };
  document.getElementById('signout').onclick = function(){
    localStorage.removeItem('id_token');
    localStorage.removeItem('access_token');
    updateUi();
  };
  document.getElementById('send').onclick = function(){
    (async function(){
      try{
        var token = localStorage.getItem('id_token');
        if(!token){ alert('Please sign in first.'); return; }
        var el = document.getElementById('goal');
        var v = el && el.value ? el.value : '';
        var goal = (typeof v === 'string' ? v : '').trim();
        if(!goal){ alert('Enter a goal.'); return; }
        var r = await fetch(apiUrl + '/v1/chat', {
          method:'POST',
          headers:{ 'Content-Type':'application/json', 'Authorization':'Bearer ' + token },
          body: JSON.stringify({ goal: goal })
        });
        var text = await r.text();
        var logEl = document.getElementById('log'); if(logEl){ logEl.textContent = text; }
      }catch(e){ console.error(e); alert('Request failed; see console'); }
    })();
  };
  </script>
</body></html>"""

        html = (
            html_template.replace("__API_URL__", json.dumps(normalized_api_url))
            .replace("__COGNITO_DOMAIN__", json.dumps(cognito_domain))
            .replace("__CLIENT_ID__", json.dumps(user_pool_client_id))
        )

        s3d.BucketDeployment(
            self,
            "DeployIndex",
            destination_bucket=site_bucket,
            distribution=dist,
            sources=[s3d.Source.data("index.html", html)],
        )

        callback_url = f"https://{dist.domain_name}/"
        cr.AwsCustomResource(
            self,
            "UpdateCognitoAppClient",
            on_update=cr.AwsSdkCall(
                service="CognitoIdentityServiceProvider",
                action="updateUserPoolClient",
                parameters={
                    "UserPoolId": user_pool_id,
                    "ClientId": user_pool_client_id,
                    "AllowedOAuthFlowsUserPoolClient": True,
                    "AllowedOAuthFlows": ["implicit"],
                    "AllowedOAuthScopes": ["openid", "email", "profile"],
                    "CallbackURLs": [callback_url],
                    "LogoutURLs": [callback_url],
                    "SupportedIdentityProviders": ["COGNITO"],
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    f"cognito-app-client-callback-{dist.distribution_id}"
                ),
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE
            ),
        )

        CfnOutput(self, "CdnUrl", value=f"https://{dist.domain_name}")
        CfnOutput(self, "BucketName", value=site_bucket.bucket_name)
