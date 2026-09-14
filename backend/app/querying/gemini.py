import base64

from google import genai

client = genai.Client()

# text
response = client.interactions.create(
    model = "gemini-2.5-flash",
    input = "Hello, can you provide a brief overview of the latest advancements in AI research?"
)

print(response.output_text)

# image generation here
prompt = "A futuristic cityscape with flying cars and neon lights, in a cyberpunk style"
response1 = client.interactions.create(
    model = "gemini-2.5-flash-image",
    input = prompt
)

print(response1.output_image)

#image editing here
with open("/path/to/cat_image.png", "rb") as f:
    image_bytes = f.read()

image1 = client.files.upload(file = "/path/to/cat_image.png")

response2 = client.interactions.create(
    model = "gemini-2.5-flash-image",
    input = [
        {
            "type" : "text",
            "text" : "Add a giant holographic advertisement in the sky"
        },
        {
            "type" : "image",
            "data" : base64.b64encode(image_bytes).decode('utf-8')
        }
    ],
    service_tier = "priority"
)

response3 = client.interactions.create(
    model = "gemini-2.5-flash-image",
    input = [
        {
            "type" : "text",
            "text" : "Add a giant holographic advertisement in the sky"
        },
        {
            "type" : "image",
            "uri" : image1.uri,
            "mime_type" : image1.mime_type
        }
    ],
    service_tier = "priority"
)

print(response2.output_image)
print(response3.output_image)