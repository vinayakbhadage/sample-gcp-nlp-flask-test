from datetime import datetime
import logging
from flask import Flask
from flask_restx import Resource, Api
from google.cloud import datastore
from google.cloud import language_v1 as language
import os

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "key.json"

"""
This Flask app shows some examples of the types of requests you could build.
There is currently a GET request that will return all the data in GCP Datastore.
There is also a POST request that will analyse some given text then store the text and its sentiment in GCP Datastore.


The sentiment analysis of the text is being done by Google's NLP API. 
This API can be used to find the Sentiment, Entities, Entity-Sentiment, Syntax, and Content-classification of texts.
Find more about this API here:
https://cloud.google.com/natural-language/docs/basics
For sample code for implementation, look here (click 'Python' above the code samples):
https://cloud.google.com/natural-language/docs/how-to
Note: The analyze_text_sentiment() method below simply copies the 'Sentiment' part of the above documentation.


The database we are using is GCP Datastore (AKA Firestore in Datastore mode). 
This is a simple NoSQL Document database offering by Google:
https://cloud.google.com/datastore
You can access the database through the GCP Cloud Console (find Datastore in the side-menu)


Some ideas of things to build:
- At the moment, the code only stores the analysis of the first sentence of a given text. Modify the POST request to
 also analyse the rest of the sentences. 
- GET Request that returns a single entity based on its ID
- POST Request that will take a list of text items and give it a sentiment then store it in GCP Datastore
- DELETE Request to delete an entity from Datastore based on its ID
- Implement the other analyses that are possible with Google's NLP API


We are using Flask: https://flask.palletsprojects.com/en/2.0.x/
Flask RESTX is an extension of Flask that allows us to document the API with Swagger: https://flask-restx.readthedocs.io/en/latest/
"""

app = Flask(__name__)
api = Api(app)

parser = api.parser()
parser.add_argument("file_uri", type=str, help="Cloud Storage File URL", location="form")
parser.add_argument("language_code", type=str, help="Language like en or de", location="form")


@api.route("/api/text")
class Text(Resource):
    def get(self):
        """
        This GET request will return all the articles and sentiments that have been POSTed previously.
        """
        # Create a Cloud Datastore client.
        datastore_client = datastore.Client()

        # Get the datastore 'kind' which are 'Sentences'
        query = datastore_client.query(kind="Articles")
        text_entities = list(query.fetch())

        # Parse the data into a dictionary format
        result = {}
        for text_entity in text_entities:
            result[str(text_entity.id)] = {
                "file_uri": str(text_entity["file_uri"]),
                "timestamp": str(text_entity["timestamp"]),
                "sentiment": str(text_entity["sentiment"]),
            }

        return result

    @api.expect(parser)
    def post(self):
        """
        This POST request will accept a 'Google Cloud storage file uri' and language code, analyze the sentiment analysis of the file content, store
        the result to datastore as a 'Articles', and also return the result.
        """
        datastore_client = datastore.Client()

        args = parser.parse_args()
        file_uri = args["file_uri"]
        language_code = args["language_code"]
        # Get the sentiment score of the first sentence of the analysis (that's the [0] part)
        sentiment = analyze_sentiment_using_uri(file_uri, language_code).get("score")

        # Assign a label based on the score
        overall_sentiment = "unknown"
        if sentiment > 0:
            overall_sentiment = "positive"
        if sentiment < 0:
            overall_sentiment = "negative"
        if sentiment == 0:
            overall_sentiment = "neutral"

        current_datetime = datetime.now()

        # The kind for the new entity. This is so all 'Sentences' can be queried.
        kind = "Articles"

        # Create a key to store into datastore
        key = datastore_client.key(kind)
        # If a key id is not specified then datastore will automatically generate one. For example, if we had:
        # key = datastore_client.key(kind, 'sample_task')
        # instead of the above, then 'sample_task' would be the key id used.

        # Construct the new entity using the key. Set dictionary values for entity
        entity = datastore.Entity(key)
        entity["file_uri"] = file_uri
        entity["timestamp"] = current_datetime
        entity["sentiment"] = overall_sentiment

        # Save the new entity to Datastore.
        datastore_client.put(entity)

        result = {}
        result[str(entity.key.id)] = {
            "file_uri": file_uri,
            "timestamp": str(current_datetime),
            "sentiment": overall_sentiment,
        }
        return result


@app.errorhandler(500)
def server_error(e):
    logging.exception("An error occurred during a request.")
    return (
        """
    An internal error occurred: <pre>{}</pre>
    See logs for full stacktrace.
    """.format(
            e
        ),
        500,
    )

def analyze_sentiment_using_uri(gcs_content_uri, language_code = "en"):
    """
    Analyzing Sentiment in text file stored in Cloud Storage

    Args:
      gcs_content_uri Google Cloud Storage URI where the file content is located.
      e.g. gs://[Your Bucket]/[Path to File]
    """

    client = language.LanguageServiceClient()

    # gcs_content_uri = 'gs://cloud-samples-data/language/sentiment-positive.txt'

    # Available types: PLAIN_TEXT, HTML
    type_ = language.Document.Type.PLAIN_TEXT

    # Optional. If not specified, the language is automatically detected.
    # For list of supported languages:
    # https://cloud.google.com/natural-language/docs/languages
#     language = "en"
    document = {"gcs_content_uri": gcs_content_uri, "type_": type_, "language": language_code}

    # Available values: NONE, UTF8, UTF16, UTF32
    encoding_type = language.EncodingType.UTF8

    response = client.analyze_sentiment(request = {'document': document, 'encoding_type': encoding_type})

    results = dict(
        text=gcs_content_uri,
        score=response.document_sentiment.score,
        magnitude=response.document_sentiment.magnitude,
    )

    return results
    # Get overall sentiment of the input document
    # print(u"Document sentiment score: {}".format(response.document_sentiment.score))
    # print(
    #     u"Document sentiment magnitude: {}".format(
    #         response.document_sentiment.magnitude
    #     )
    # )
    # Get sentiment for all sentences in the document
#     for sentence in response.sentences:
#         print(u"Sentence text: {}".format(sentence.text.content))
#         print(u"Sentence sentiment score: {}".format(sentence.sentiment.score))
#         print(u"Sentence sentiment magnitude: {}".format(sentence.sentiment.magnitude))

    # Get the language of the text, which will be the same as
    # the language specified in the request or, if not specified,
    # the automatically-detected language.
    # print(u"Language of the text: {}".format(response.language))

def analyze_text_sentiment(text):
    """
    This is modified from the Google NLP API documentation found here:
    https://cloud.google.com/natural-language/docs/analyzing-sentiment
    It makes a call to the Google NLP API to retrieve sentiment analysis.
    """
    client = language.LanguageServiceClient()
    document = language.Document(content=text, type_=language.Document.Type.PLAIN_TEXT)

    response = client.analyze_sentiment(document=document)

    # Format the results as a dictionary
    sentiment = response.document_sentiment
    results = dict(
        text=text,
        score=f"{sentiment.score:.1%}",
        magnitude=f"{sentiment.magnitude:.1%}",
    )

    # Print the results for observation
    for k, v in results.items():
        print(f"{k:10}: {v}")

    # Get sentiment for all sentences in the document
    sentence_sentiment = []
    for sentence in response.sentences:
        item = {}
        item["text"] = sentence.text.content
        item["sentiment score"] = sentence.sentiment.score
        item["sentiment magnitude"] = sentence.sentiment.magnitude
        sentence_sentiment.append(item)

    return sentence_sentiment


if __name__ == "__main__":
    # This is used when running locally. Gunicorn is used to run the
    # application on Google App Engine. See entrypoint in app.yaml.
    app.run(host="127.0.0.1", port=8080, debug=True)
