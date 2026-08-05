# Alpaca
Alpaca is a command line tool to test out oasis models on EC2 servers.
For a list of all the commands that are available for Alpaca, simply typing the command
`alpaca`
will list all currently available options.

## AWS Login
Alpaca uses boto3 to connect to AWS. To allow your AWS account to be accessed to create
the instance, boto3 will require either you to have the environment variables
`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
both set, or to have credentials in a .aws folder, which can be obtained with the command
`aws configure` using the aws cli.

## Connecting to instances
Alpaca connects to instances entirely over AWS Systems Manager (SSM) rather than a static
`.pem` key, so there's no `KEY_NAME` / `KEY_PATH` config or key file to manage. Each run
generates a throwaway SSH keypair in memory, authorises it on the instance for 60 seconds via
EC2 Instance Connect, and tunnels the SSH session through
`aws ssm start-session --document-name AWS-StartSSHSession`.

A few things need to be in place for that to work:

* **On your machine**: both the AWS CLI v2 and the
  [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html)
  must be installed and on your `PATH`. Alpaca shells out to `aws ssm start-session`, so if
  either is missing you will see connection attempts time out rather than a clear error.
* **Your AWS user or role** needs `ssm:StartSession` (on the instance and on the
  `AWS-StartSSHSession` document), `ssm:DescribeInstanceInformation` and
  `ec2-instance-connect:SendSSHPublicKey` in addition to the usual EC2 permissions. This is new:
  with `.pem` keys, connecting needed no SSM or Instance Connect permissions at all.
* **`IAM_INSTANCE_PROFILE`** is now a required config value, and the role behind it must let the
  SSM Agent register. The `AmazonSSMManagedInstanceCore` managed policy is enough, alongside
  whatever S3 access your run needs.
* **`AMI_ID`** must point at an image with both the SSM Agent and the `ec2-instance-connect`
  package preinstalled. Canonical's Ubuntu 20.04+ and Amazon Linux 2 images have both; a
  stripped-down custom image may not, and the failure looks like Alpaca waiting out its retries.
* **`SECURITY_GROUP_ID`** no longer needs an inbound port 22 rule, as nothing connects to the
  instance directly. Only outbound access is required (for pip, GitHub and S3).

If your AWS CLI uses a named profile, set the optional `AWS_PROFILE` config value; it is applied
to both the boto3 calls and the SSM tunnel.

## Config
To use Alpaca, first create an alpaca config. This can be easily done by the command
`alpaca create-config`
which will list all subcommands available (config varies by type).
Examples of Alpaca config can be found in the `example_configs` folder, and the config
creation tool will assist you in creating your own by providing help text and defaults
for all given options.

To override config that is missing from your config file, you can set the environment
variable
`ALPACA_{config}`
which will replace the config if it is missing from your config file.
Please note that `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are boto3 environment
variables and not Alpaca ones and will not have the `ALPACA_` prefix.

## Running a model
When you have created your config file, to use it to perform an Oasis model run, simply
use the command
`alpaca model <path-to-config>`
to watch your instance be spun up and your results saved either back to your computer or
up in S3 depending on your configuration.

## Running pytests
Simply use the command
`alpaca pytest <path-to-config>`
to do the same thing with any tests you have for a model.

## Running on the platform
For the platform run, your repo must either have a docker compose file or a deployment
bash script that will start your platform. When you have created your config, use the
command
`alpaca api <path-to-config>`
to create a platform in EC2 and do an API run.

## Debug mode
Setting the optional config value `DEBUG` to `True` (or `ALPACA_DEBUG=True` in the
environment) steps through the run one command at a time. Before each command Alpaca
would normally run, you are shown it and asked what to do:

* **Enter** or **x** runs the command and moves on to the next one.
* **s** skips the command entirely.
* **t** terminates the instance and stops the run.
* **anything else** is run on the instance as a command of your own, after which you are
  asked about the same command again. Use this to look around the instance, fix something
  by hand, or try a variant of the command before letting the run continue. Your input
  reaches Alpaca but not the command, so anything that waits for input of its own (an
  editor, a password prompt, `top`) will hang with no way out but Ctrl-C.

Every command's output is streamed to your terminal in debug mode, including the ones that
are normally logged only at debug level. Note that the prompt starts at the very first
setup command, so you will step through the Python and OasisLMF install before reaching
your model run, and that a failing command does not stop the run as it otherwise would:
in debug mode it is up to you to decide whether to carry on. Debug mode needs a terminal
to read from, so it cannot be used for an unattended or CI run.

## Notes
Alpaca is currently designed to be ran on instances using Ubuntu. This can be changed in
the future, but only Ubuntu instances will currently work due to the path /home/ubuntu
being used as a default.
```
              04515                                           # # #
              2 52 3     x               x                       #   #
             1473173    x x             x x                       #   #
         75   44   2     x               x                        #   #
          41       13                                            #   #
              3    13           x                             # # #
   x          3     5          x x                      #
  x x        27     17          x             x        # #
   x        72      17                       x x     #     #
            75      11                        x     #       #         x
            3        464455444451                 #           #      x x
            2         27771771132  13            #             #      x
            2         3 73 37 5 37 715         #                 #
            2         3        711 7137       #                   #
            3         353435225157 735      #         OASIS         #
            12                     71      #           LMF           #
              3            732665  71    #                             #
               71  227 27   5  32  71   #                               #
               73  317 4    4  13  17 #                                   #
                3  317 4    4 713  2 #                                     #
                2  33772    4 713  4
                2 27371     4 373 17
                2 4 272     435 2 2
```
