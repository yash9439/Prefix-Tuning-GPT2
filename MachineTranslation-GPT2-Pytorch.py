# -*- coding: utf-8 -*-
"""3.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1RFPbmr-WrIVQ3WMeDRmacAzP-6olEyyQ
"""

import warnings

# Ignore all warnings
warnings.filterwarnings('ignore')

import torch
from torch.utils.data import DataLoader, TensorDataset
from transformers import GPT2LMHeadModel, GPT2Tokenizer
import pandas as pd
from datasets import load_dataset
import nltk
from nltk.translate.bleu_score import corpus_bleu


# Constants
MODEL_NAME = "gpt2"
BATCH_SIZE = 1
EPOCHS = 1
PROMPT_TOKEN = "[TRANSLATE]"
MAX_LEN = 500

# Soft Prompt Vocabulary
soft_prompt_vocab = ["[TRANSLATE]"]  # Define your custom vocabulary here

# Create a word2idx dictionary for the soft prompt vocabulary
soft_prompt_word2idx = {word: idx for idx, word in enumerate(soft_prompt_vocab)}

num_prompts = len([soft_prompt_word2idx[word] for word in PROMPT_TOKEN.split()])
prompt_id = torch.tensor([soft_prompt_word2idx[word] for word in PROMPT_TOKEN.split()])

# Model Architecture
class GPT2WithSoftPrompt(torch.nn.Module):
    def __init__(self, model_name, num_prompts, embedding_size=768):
        super().__init__()
        self.gpt2 = GPT2LMHeadModel.from_pretrained(model_name)
        self.soft_prompt = torch.nn.Embedding(num_prompts, embedding_size)

    def forward(self, input_ids, prompt_ids):
        prompt_embeddings = self.soft_prompt(prompt_ids)
        base_embeddings = self.gpt2.transformer.wte(input_ids)
        embeddings = torch.cat([prompt_embeddings, base_embeddings.squeeze(0)], dim=0)
        outputs = self.gpt2(inputs_embeds=embeddings)
        return outputs


def load_data_from_files(english_file, german_file):
    with open(english_file, "r", encoding="utf-8") as eng_file:
        english_list = eng_file.readlines()

    with open(german_file, "r", encoding="utf-8") as ger_file:
        german_list = ger_file.readlines()

    return english_list[:600], german_list[:600]


# Data Loading and Preprocessing
def load_and_preprocess_data(english_file, german_file, num_prompts):
    english_list, german_list = load_data_from_files(english_file, german_file)

    # Perform preprocessing on the data
    tokenized_english = []
    tokenized_german = []

    tokenizer = GPT2Tokenizer.from_pretrained(MODEL_NAME)

    for english_sentence, german_sentence in zip(english_list, german_list):
        english_tokens = tokenizer.encode(english_sentence, truncation=True, max_length=MAX_LEN)
        german_tokens = tokenizer.encode(german_sentence, truncation=True, max_length=MAX_LEN)

        # Pad the sequences to MAX_LEN
        padded_english = english_tokens + [tokenizer.eos_token_id] * (MAX_LEN-1 - len(english_tokens))
        padded_german = german_tokens + [tokenizer.eos_token_id] * (MAX_LEN - len(german_tokens))

        tokenized_english.append(padded_english)
        tokenized_german.append(padded_german)

    return tokenized_english, tokenized_german

# Load and preprocess the data
tokenizer = GPT2Tokenizer.from_pretrained(MODEL_NAME)

tokenized_articles_total , tokenized_summaries_total = load_and_preprocess_data("europarl-v7.de-en.en", "europarl-v7.de-en.de",num_prompts)
total_samples = len(tokenized_articles_total)
split_ratio = [0.8, 0.1, 0.1]

# Calculate the sizes of the three sets
train_size = int(total_samples * split_ratio[0])
val_size = int(total_samples * split_ratio[1])
test_size = int(total_samples * split_ratio[2])

# Split the data
tokenized_articles_train = tokenized_articles_total[:train_size]
tokenized_summaries_train = tokenized_summaries_total[:train_size]

tokenized_articles_validation = tokenized_articles_total[train_size:train_size + val_size]
tokenized_summaries_validation = tokenized_summaries_total[train_size:train_size + val_size]

tokenized_articles_test = tokenized_articles_total[train_size + val_size:]
tokenized_summaries_test = tokenized_summaries_total[train_size + val_size:]

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# # Model Initialization
model = GPT2WithSoftPrompt(MODEL_NAME, num_prompts).to(device)

from tqdm import tqdm

# Hyperparameters
BATCH_SIZE = 1
EPOCHS = 10
GRADIENT_ACCUMULATION_STEPS = 1
GRADIENT_CLIP_NORM = 1.0
EARLY_STOPPING_PATIENCE = 2
prompt_id = prompt_id.to(device)
# Import cross_entropy_loss
from torch.nn import CrossEntropyLoss

def fine_tune_on_summarization(model, train_articles, train_summaries, val_articles, val_summaries, test_articles, test_summaries):
    optimizer = torch.optim.Adam(model.soft_prompt.parameters())

    best_val_loss = float('inf')
    no_improvement_epochs = 0

    for epoch in range(EPOCHS):
        model.train()

        # Gradient accumulation initialization
        optimizer.zero_grad()
        accumulated_loss = 0
        loss = 0
        # Use tqdm for progress bar
        with tqdm(enumerate(zip(train_articles, train_summaries)), total=len(train_articles), desc=f"Epoch {epoch + 1}/{EPOCHS}", unit="batch") as progress:
            train_percentage_matched = 0
            train_percentage_matched_ct = 0
            train_pred_sentences = []
            train_true_sentences = []
            for idx, (article, summary) in progress:
                input_ids = torch.tensor(article).to(device)
                labels = torch.tensor(summary).to(device)
                outputs = model(input_ids, prompt_id)

                # Bleu Score
                pred_logits = outputs.logits
                predicted_token_ids = torch.argmax(pred_logits, dim=-1)
                predicted_tokens = tokenizer.decode(predicted_token_ids, skip_special_tokens=True)
                train_pred_sentences.append(predicted_tokens.split())
                predicted_tokens = tokenizer.decode(labels, skip_special_tokens=True)
                train_true_sentences.append(predicted_tokens.split())


                ignore_index = tokenizer.eos_token_id
                loss += CrossEntropyLoss(ignore_index=ignore_index)(outputs.logits, labels)

                # Metrics
                set1 = set(torch.argmax(outputs.logits, dim=1).cpu().numpy())
                set2 = set(labels.cpu().numpy())

                # Calculate the intersection of sets
                intersection = set1.intersection(set2)

                # Calculate the percentage of indices in the first tensor that are also in the second tensor
                percentage = (len(intersection) / len(set1)) * 100
                train_percentage_matched += percentage
                train_percentage_matched_ct += 1

                # Backpropagate losses every GRADIENT_ACCUMULATION_STEPS or at the end of the dataset
                if (idx + 1) % GRADIENT_ACCUMULATION_STEPS == 0 or idx == len(train_articles) - 1:
                    (loss / GRADIENT_ACCUMULATION_STEPS).backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), GRADIENT_CLIP_NORM)
                    optimizer.step()
                    optimizer.zero_grad()
                    loss = 0

            print("Train : % Exact Match: ",train_percentage_matched/train_percentage_matched_ct)
            try:
                bleu_score = corpus_bleu(train_true_sentences, train_pred_sentences)
                print(f'Train BLEU Score: {bleu_score}')
            except:
                pass


        # Validation
        model.eval()
        total_val_loss = 0
        val_pred_sentences = []
        val_true_sentences = []
        with torch.no_grad():
            val_percentage_matched = 0
            val_percentage_matched_ct = 0
            for article, summary in tqdm(zip(val_articles, val_summaries), total=len(val_articles), desc="Validation", unit="batch"):
                input_ids = torch.tensor(article).to(device)
                labels = torch.tensor(summary).to(device)
                outputs = model(input_ids, prompt_id)

                # Bleu Score
                pred_logits = outputs.logits
                predicted_token_ids = torch.argmax(pred_logits, dim=-1)
                predicted_tokens = tokenizer.decode(predicted_token_ids, skip_special_tokens=True)
                val_pred_sentences.append(predicted_tokens.split())
                predicted_tokens = tokenizer.decode(labels, skip_special_tokens=True)
                val_true_sentences.append(predicted_tokens.split())

                ignore_index = tokenizer.eos_token_id if tokenizer.eos_token_id is not None else -100
                val_loss = CrossEntropyLoss(ignore_index=ignore_index)(outputs.logits, labels)
                total_val_loss += val_loss.item()

                # Metrics
                set1 = set(torch.argmax(outputs.logits, dim=1).cpu().numpy())
                set2 = set(labels.cpu().numpy())

                # Calculate the intersection of sets
                intersection = set1.intersection(set2)

                # Calculate the percentage of indices in the first tensor that are also in the second tensor
                percentage = (len(intersection) / len(set1)) * 100
                val_percentage_matched += percentage
                val_percentage_matched_ct += 1


        print("Val : % Exact Match: ",val_percentage_matched/val_percentage_matched_ct)
        avg_val_loss = total_val_loss / len(val_articles)
        print("Val Loss : ",avg_val_loss)
        bleu_score = corpus_bleu(val_true_sentences, val_pred_sentences)
        print(f'Val BLEU Score: {bleu_score}')

        # Early stopping
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            no_improvement_epochs = 0
        else:
            no_improvement_epochs += 1
            if no_improvement_epochs >= EARLY_STOPPING_PATIENCE:
                print(f"Early stopping after {EARLY_STOPPING_PATIENCE} epochs without improvement.")
                break

    # Testing
    model.eval()
    test_pred_sentences = []
    test_true_sentences = []
    total_test_loss = 0
    with torch.no_grad():
        test_percentage_matched = 0
        test_percentage_matched_ct = 0
        for article, summary in tqdm(zip(test_articles, test_summaries), total=len(test_articles), desc="Validation", unit="batch"):
            input_ids = torch.tensor(article).to(device)
            labels = torch.tensor(summary).to(device)
            outputs = model(input_ids, prompt_id)

            # Bleu Score
            pred_logits = outputs.logits
            predicted_token_ids = torch.argmax(pred_logits, dim=-1)
            predicted_tokens = tokenizer.decode(predicted_token_ids, skip_special_tokens=True)
            test_pred_sentences.append(predicted_tokens.split())
            predicted_tokens = tokenizer.decode(labels, skip_special_tokens=True)
            test_true_sentences.append(predicted_tokens.split())

            ignore_index = tokenizer.eos_token_id if tokenizer.eos_token_id is not None else -100
            test_loss = CrossEntropyLoss(ignore_index=ignore_index)(outputs.logits, labels)
            total_test_loss += test_loss.item()

            # Metrics
            set1 = set(torch.argmax(outputs.logits, dim=1).cpu().numpy())
            set2 = set(labels.cpu().numpy())

            # Calculate the intersection of sets
            intersection = set1.intersection(set2)

            # Calculate the percentage of indices in the first tensor that are also in the second tensor
            percentage = (len(intersection) / len(set1)) * 100
            test_percentage_matched += percentage
            test_percentage_matched_ct += 1


        print("Test : % Exact Match: ",test_percentage_matched/test_percentage_matched_ct)
        avg_test_loss = total_test_loss / len(test_articles)
        print("Test Loss : ",avg_test_loss)
        bleu_score = corpus_bleu(test_true_sentences, test_pred_sentences)
        print(f'Test BLEU Score: {bleu_score}')


    return model

fine_tuned_model = fine_tune_on_summarization(model, tokenized_articles_train, tokenized_summaries_train, tokenized_articles_validation, tokenized_summaries_validation, tokenized_articles_test, tokenized_summaries_test)

"""# Saving Model"""

# Save the fine-tuned model
torch.save(fine_tuned_model.state_dict(), '3.pth')

"""# Loading Model"""

# Initialize a new instance of the model
model = GPT2WithSoftPrompt(MODEL_NAME, num_prompts).to(device)

# Load the saved model state_dict
model.load_state_dict(torch.load('3.pth'))

# Make sure the model is in evaluation mode after loading
model.eval()

"""# Inference"""

# Set the model to evaluation mode
model.eval()

# Input text for summarization
input_text = "Madam President, on a point of order."

# Tokenize and encode the input text
input_ids = tokenizer.encode(input_text, truncation=True, max_length=1024)

# Convert the input_ids to a PyTorch tensor
input_ids = torch.tensor(input_ids)

# Generate a summary
with torch.no_grad():
    # Assuming single prompt
    outputs = model(input_ids.to(device), prompt_ids=prompt_id.to(device))
    pred_logits = outputs.logits
    print(pred_logits.shape)


# Get the token IDs with the highest probability for each position
predicted_token_ids = torch.argmax(pred_logits, dim=-1)

# Convert token IDs into words using the tokenizer
predicted_tokens = tokenizer.decode(predicted_token_ids.squeeze(0), skip_special_tokens=True)

predicted_tokens

"""# Hard Prompt"""

import torch
from torch.utils.data import DataLoader, TensorDataset
from transformers import GPT2LMHeadModel, GPT2Tokenizer
import pandas as pd
from datasets import load_dataset
import nltk
from nltk.translate.bleu_score import corpus_bleu


# Constants
MODEL_NAME = "gpt2"
BATCH_SIZE = 1
EPOCHS = 1
PROMPT_TOKEN = "Translate the following sentence from english to german :"
MAX_LEN = 500

# Soft Prompt Vocabulary
soft_prompt_vocab = ["Translate","the","following","sentence","from","english","to","german",":"]  # Define your custom vocabulary here

# Create a word2idx dictionary for the soft prompt vocabulary
soft_prompt_word2idx = {word: idx for idx, word in enumerate(soft_prompt_vocab)}

num_prompts = len([soft_prompt_word2idx[word] for word in PROMPT_TOKEN.split()])
prompt_id = torch.tensor([soft_prompt_word2idx[word] for word in PROMPT_TOKEN.split()])

# Model Architecture
class GPT2WithSoftPrompt(torch.nn.Module):
    def __init__(self, model_name, num_prompts, embedding_size=768):
        super().__init__()
        self.gpt2 = GPT2LMHeadModel.from_pretrained(model_name)
        self.soft_prompt = torch.nn.Embedding(num_prompts, embedding_size)

    def forward(self, input_ids, prompt_ids):
        prompt_embeddings = self.soft_prompt(prompt_ids)
        base_embeddings = self.gpt2.transformer.wte(input_ids)
        embeddings = torch.cat([prompt_embeddings, base_embeddings.squeeze(0)], dim=0)
        outputs = self.gpt2(inputs_embeds=embeddings)
        return outputs


def load_data_from_files(english_file, german_file):
    with open(english_file, "r", encoding="utf-8") as eng_file:
        english_list = eng_file.readlines()

    with open(german_file, "r", encoding="utf-8") as ger_file:
        german_list = ger_file.readlines()

    return english_list[:1500], german_list[:150]


# Data Loading and Preprocessing
def load_and_preprocess_data(english_file, german_file, num_prompts):
    english_list, german_list = load_data_from_files(english_file, german_file)

    # Perform preprocessing on the data
    tokenized_english = []
    tokenized_german = []

    tokenizer = GPT2Tokenizer.from_pretrained(MODEL_NAME)

    for english_sentence, german_sentence in zip(english_list, german_list):
        english_tokens = tokenizer.encode(english_sentence, truncation=True, max_length=MAX_LEN)
        german_tokens = tokenizer.encode(german_sentence, truncation=True, max_length=MAX_LEN)

        # Pad the sequences to MAX_LEN
        padded_english = english_tokens + [tokenizer.eos_token_id] * (MAX_LEN - len(english_tokens))
        padded_german = german_tokens + [tokenizer.eos_token_id] * (MAX_LEN+9 - len(german_tokens))

        tokenized_english.append(padded_english)
        tokenized_german.append(padded_german)

    return tokenized_english, tokenized_german

# Load and preprocess the data
tokenizer = GPT2Tokenizer.from_pretrained(MODEL_NAME)

tokenized_articles_total , tokenized_summaries_total = load_and_preprocess_data("europarl-v7.de-en.en", "europarl-v7.de-en.de",num_prompts)
total_samples = len(tokenized_articles_total)
split_ratio = [0.8, 0.1, 0.1]

# Calculate the sizes of the three sets
train_size = int(total_samples * split_ratio[0])
val_size = int(total_samples * split_ratio[1])
test_size = int(total_samples * split_ratio[2])

# Split the data
tokenized_articles_train = tokenized_articles_total[:train_size]
tokenized_summaries_train = tokenized_summaries_total[:train_size]

tokenized_articles_validation = tokenized_articles_total[train_size:train_size + val_size]
tokenized_summaries_validation = tokenized_summaries_total[train_size:train_size + val_size]

tokenized_articles_test = tokenized_articles_total[train_size + val_size:]
tokenized_summaries_test = tokenized_summaries_total[train_size + val_size:]

device = "cpu"


# # Model Initialization
model = GPT2WithSoftPrompt(MODEL_NAME, num_prompts).to(device)

from torch.nn import CrossEntropyLoss
from tqdm import tqdm

# Testing
model.eval()
test_pred_sentences = []
test_true_sentences = []
total_test_loss = 0
with torch.no_grad():
    test_percentage_matched = 0
    test_percentage_matched_ct = 0
    for article, summary in tqdm(zip(tokenized_articles_test, tokenized_summaries_test), total=len(tokenized_articles_test), desc="Validation", unit="batch"):
        input_ids = torch.tensor(article).to(device)
        labels = torch.tensor(summary).to(device)
        outputs = model(input_ids, prompt_id)

        # Bleu Score
        pred_logits = outputs.logits
        predicted_token_ids = torch.argmax(pred_logits, dim=-1)
        predicted_tokens = tokenizer.decode(predicted_token_ids, skip_special_tokens=True)
        test_pred_sentences.append(predicted_tokens.split())
        predicted_tokens = tokenizer.decode(labels, skip_special_tokens=True)
        test_true_sentences.append(predicted_tokens.split())

        ignore_index = tokenizer.eos_token_id if tokenizer.eos_token_id is not None else -100
        test_loss = CrossEntropyLoss(ignore_index=ignore_index)(outputs.logits, labels)
        total_test_loss += test_loss.item()

        # Metrics
        set1 = set(torch.argmax(outputs.logits, dim=1).cpu().numpy())
        set2 = set(labels.cpu().numpy())

        # Calculate the intersection of sets
        intersection = set1.intersection(set2)

        # Calculate the percentage of indices in the first tensor that are also in the second tensor
        percentage = (len(intersection) / len(set1)) * 100
        test_percentage_matched += percentage
        test_percentage_matched_ct += 1


print("Test : % Exact Match: ",test_percentage_matched/test_percentage_matched_ct)
avg_test_loss = total_test_loss / len(tokenized_summaries_test)
print("Test Loss : ",avg_test_loss)
bleu_score = corpus_bleu(test_true_sentences, test_pred_sentences)
print(f'Test BLEU Score: {bleu_score}')

