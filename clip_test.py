import torch
import clip
from PIL import Image
import requests
import matplotlib.pyplot as plt

# Load CLIP model
device = "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)

# Load an image
image_path = "~/Desktop/swastika.png"
image = Image.open(image_path)

# Show the image
# plt.imshow(image)
# plt.axis("off")
# plt.show()

# Preprocess the image for CLIP
image_input = preprocess(image).unsqueeze(0).to(device)

# Define text descriptions for classification
text_descriptions = [
    "a swastika",
    "an octopus",
    "a birds eye view of a town"
]

# tokenize text
text_inputs = clip.tokenize(text_descriptions).to(device)

with torch.no_grad():
    image_features = model.encode_image(image_input)
    text_features = model.encode_text(text_inputs)
    similarity = (image_features @ text_features.T).softmax(dim=-1)

best_match_idx = similarity.argmax().item()

print(f"CLIP thinks this image is: {text_descriptions[best_match_idx]} (confidence: {similarity[0][best_match_idx]:.2f})")
