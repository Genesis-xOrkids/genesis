#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { GithubOidcStack } from "../lib/github-oidc-stack";

const app = new cdk.App();

// Account and region come from the ambient AWS credentials rather than being
// hardcoded, so the same app deploys to a personal sandbox and to production
// without an edit.
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION ?? "us-east-1",
};

new GithubOidcStack(app, "GenesisGithubOidc", {
  env,
  repository: "ty-c1016/genesis",
  branch: "main",
  description: "GitHub Actions OIDC trust for Genesis deploys (no billable resources)",
});

cdk.Tags.of(app).add("project", "genesis");
cdk.Tags.of(app).add("managed-by", "cdk");
