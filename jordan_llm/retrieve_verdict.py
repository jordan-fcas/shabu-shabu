import urllib.request
import re
import tiktoken
import torch
from torch.utils.data import Dataset, DataLoader
from tokenizer import SimpleTokenizerV2
from jordan_torch import GPTDatasetV1

# url = ("https://raw.githubusercontent.com/rasbt/"
#        "LLMs-from-scratch/main/ch02/01_main-chapter-code/"
#        "the-verdict.txt")

# file_path = "the-verdict.txt"

# urllib.request.urlretrieve(url, file_path)

with open("the-verdict.txt", "r", encoding="utf-8") as f:
    raw_text = f.read()

# print("Total number of characters: ", len(raw_text))
# print(raw_text[:99])

# preprocessed = re.split(r'([,.:;?_!"()\']|--|\s)', raw_text)
# preprocessed = [item.strip() for item in preprocessed if item.strip()]
# # print(len(preprocessed))
# # print(preprocessed[:30])

# all_tokens = sorted(set(preprocessed))
# all_tokens.extend(["<|endoftext|>", "<|unk|>"])

# vocab = {token:integer for integer,token in enumerate(all_tokens)}
# for i, item in enumerate(vocab.items()):
#     print(item)
#     if i >= 50:
#         break
# text = (
#     "Akwirw ier"
# )

# tokenizer = SimpleTokenizerV2(vocab)
# ids = tokenizer.encode(text)
# print(ids)
# print(tokenizer.decode(ids))

tiktokenizer = tiktoken.get_encoding("gpt2")

enc_text = tiktokenizer.encode(raw_text)
# print(len(enc_text))
enc_sample = enc_text[50:]

context_size = 4
# x = enc_sample[:context_size]
# y = enc_sample[1:context_size+1]
# print(f"x: {x}")
# print(f"y:      {y}")

# for i in range(1, context_size+1):
#     context = enc_sample[:i]
#     desired = enc_sample[i]
#     print(tiktokenizer.decode(context), "------>", tiktokenizer.decode([desired]))


# integers = tiktokenizer.encode(text, allowed_special={"<|endoftext|>"})
# print(integers)

# strings = tiktokenizer.decode(integers)
# print(strings)

vocab_size = 50257
output_dim = 256
token_embedding_layer = torch.nn.Embedding(vocab_size, output_dim)
max_length = 4

dataloader = GPTDatasetV1.create_dataloader_v1(
    raw_text, batch_size=8, max_length=max_length, stride=4, shuffle=False)
data_iter = iter(dataloader)
inputs, targets = next(data_iter)
# print("Token IDs:\n", inputs)
# print("\nInputs shape:\n", inputs.shape)

token_embeddings = token_embedding_layer(inputs)
print(token_embeddings.shape)

context_length = max_length
pos_embedding_layer = torch.nn.Embedding(context_length, output_dim)
pos_embeddings = pos_embedding_layer(torch.arange(context_length))
print(pos_embeddings.shape)

input_embeddings = token_embeddings + pos_embeddings
print(input_embeddings.shape)