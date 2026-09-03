import * as cdk from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import type { Construct } from "constructs";

export interface GithubOidcStackProps extends cdk.StackProps {
  /** GitHub owner and repository, e.g. "ty-c1016/genesis". */
  readonly repository: string;
  /** Branch permitted to assume the deploy role. */
  readonly branch: string;
}

/**
 * Lets GitHub Actions deploy without any stored AWS credentials.
 *
 * Actions exchanges a short-lived OIDC token for temporary AWS credentials, so
 * there is no access key sitting in repository secrets to leak, rotate, or
 * forget. The trust policy is scoped to one repository and one branch: a fork,
 * a pull request from a fork, or a different branch cannot assume this role even
 * with a valid GitHub token.
 *
 * This stack creates no billable resources.
 */
export class GithubOidcStack extends cdk.Stack {
  public readonly deployRole: iam.Role;

  constructor(scope: Construct, id: string, props: GithubOidcStackProps) {
    super(scope, id, props);

    const provider = new iam.OpenIdConnectProvider(this, "GithubProvider", {
      url: "https://token.actions.githubusercontent.com",
      clientIds: ["sts.amazonaws.com"],
    });

    this.deployRole = new iam.Role(this, "DeployRole", {
      roleName: "genesis-github-deploy",
      description: "Assumed by GitHub Actions to deploy Genesis infrastructure",
      // One hour. Long enough for a deploy, short enough that a leaked
      // credential expires before it is useful.
      maxSessionDuration: cdk.Duration.hours(1),
      assumedBy: new iam.WebIdentityPrincipal(provider.openIdConnectProviderArn, {
        StringEquals: {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
        },
        // Pinned to a branch rather than the repository as a whole. Without the
        // sub condition any workflow in any repository could assume this role.
        StringLike: {
          "token.actions.githubusercontent.com:sub": `repo:${props.repository}:ref:refs/heads/${props.branch}`,
        },
      }),
    });

    // Deploys happen through CloudFormation, so the role needs permission to
    // assume the bootstrap roles rather than broad service permissions of its
    // own. CDK's bootstrap stack owns what those roles may actually do, which
    // keeps the blast radius in one reviewable place.
    this.deployRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["sts:AssumeRole"],
        resources: [`arn:aws:iam::${this.account}:role/cdk-*`],
      }),
    );

    new cdk.CfnOutput(this, "DeployRoleArn", {
      value: this.deployRole.roleArn,
      description: "Set as AWS_DEPLOY_ROLE_ARN in the GitHub repository",
    });
  }
}
