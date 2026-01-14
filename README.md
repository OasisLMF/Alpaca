# Alpaca
Alpaca is a command line tool to test out oasis models on EC2 servers.
For a list of all the commands that are available for Alpaca, simply typing the commmand
`alpaca`
will list all currently available options.

## AWS Login
Alpaca uses boto3 to connect to AWS. To allow your AWS account to be accessed to create
the instance, boto3 will require either you to have the environment variables
`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
both set, or to have credentials in a .aws folder, which can be obtained with the command
`aws configure`.

## Config
To use Alpaca, first create an alpaca config. This can be easily done by the command
`alpaca create-config`.
which will list all subcommands available (config varies by type).
Examples of Alpaca config can be found in the `example_configs` folder, and the config
creation tool will assist you in creating your own by providing help text and defaults
for all given options.

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
Soon to be implemented

## Notes
Alpaca is currently designed to be ran on instances using Ubuntu. This can be changed in
the future, but only Ubuntu instances will currently work due to the path /home/ubuntu
being used as a default.
