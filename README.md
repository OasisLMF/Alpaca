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
`.pem` key, so there's no `KEY_NAME` / `KEY_PATH` config or key file to manage. This does mean
your local machine needs the AWS CLI v2 and Session Manager plugin installed, and
`IAM_INSTANCE_PROFILE` is now a required config value with SSM permissions attached (e.g. the
`AmazonSSMManagedInstanceCore` managed policy). If your AWS CLI uses a named profile, set the
optional `AWS_PROFILE` config value to match.

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
