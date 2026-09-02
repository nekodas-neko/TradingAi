# ask-deepseek.ps1
# Send a prompt to DeepSeek's API and print the response.
#
# Usage:
#   .\scripts\ask-deepseek.ps1 "your prompt"
#   .\scripts\ask-deepseek.ps1 "your prompt" deepseek-v4-flash
#
# Requires the DEEPSEEK_API_KEY environment variable to be set.
# Optionally set DEEPSEEK_MODEL to change the default model.

param(
    [Parameter(Mandatory = $true)][string]$Prompt,
    [string]$Model = $env:DEEPSEEK_MODEL
)

if (-not $Model) { $Model = "deepseek-v4-pro" }

$key = $env:DEEPSEEK_API_KEY
if (-not $key) {
    Write-Error "DEEPSEEK_API_KEY is not set. Run: setx DEEPSEEK_API_KEY `"<your key>`""
    exit 1
}

$body = @{
    model    = $Model
    messages = @(@{ role = "user"; content = $Prompt })
    stream   = $false
} | ConvertTo-Json -Depth 5

try {
    $resp = Invoke-RestMethod `
        -Uri "https://api.deepseek.com/chat/completions" `
        -Method Post `
        -Headers @{ Authorization = "Bearer $key" } `
        -ContentType "application/json" `
        -Body $body
}
catch {
    $detail = $_.ErrorDetails.Message
    Write-Error "DeepSeek request failed: $($_.Exception.Message)"
    if ($detail) { Write-Error $detail }
    exit 1
}

$resp.choices[0].message.content

if ($resp.usage) {
    Write-Output ""
    Write-Output "---"
    Write-Output "DeepSeek tokens — prompt: $($resp.usage.prompt_tokens), completion: $($resp.usage.completion_tokens), total: $($resp.usage.total_tokens)"
}
