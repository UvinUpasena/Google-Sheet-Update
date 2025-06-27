pipeline {
    agent any

    environment {
        AWS_REGION = 'ap-south-1'
        LAMBDA_FUNCTION_NAME = 'your-lambda-function-name'
    }

    stages {
        stage('Clone Repo') {
            steps {
                git credentialsId: 'github-ssh-creds',
                    url: 'git@github.com:uthsarauvin@gmail.com/your-repo.git',
                    branch: 'main'
            }
        }

        stage('Install Dependencies for Layer') {
            steps {
                sh '''
                mkdir -p layer/python/lib/python3.13/site-packages
                docker run --rm -v "$PWD/layer":/var/task public.ecr.aws/lambda/python:3.13 \
                  /bin/sh -c "pip install -r /var/task/requirements.txt -t /var/task/python/lib/python3.13/site-packages/"
                '''
            }
        }

        stage('Zip Lambda Code') {
            steps {
                sh '''
                cd lambda_function
                zip -r ../lambda_function.zip .
                '''
            }
        }

        stage('Zip Layer') {
            steps {
                sh '''
                cd layer
                zip -r ../lambda_layer.zip python
                '''
            }
        }

        stage('Deploy Lambda Code') {
            steps {
                sh '''
                aws lambda update-function-code \
                  --function-name $LAMBDA_FUNCTION_NAME \
                  --zip-file fileb://lambda_function.zip \
                  --region $AWS_REGION
                '''
            }
        }

        stage('Deploy Lambda Layer') {
            steps {
                sh '''
                aws lambda publish-layer-version \
                  --layer-name my-custom-layer \
                  --zip-file fileb://lambda_layer.zip \
                  --compatible-runtimes python3.13 \
                  --region $AWS_REGION
                '''
            }
        }
    }
}
