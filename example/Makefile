LOG_GROUP = $(shell aws logs describe-log-groups --region us-east-1 | jq -r '.logGroups[].logGroupName' | grep slackbot | fzf --no-info --reverse )

logs:
	aws logs tail --region us-east-1 --follow $(LOG_GROUP)

validate:
	terraform fmt -check
	terraform init -backend=false
	AWS_REGION=us-east-1 terraform validate

apply: | .terraform
	terraform apply

.PHONY: logs validate apply

.terraform:
	terraform init
