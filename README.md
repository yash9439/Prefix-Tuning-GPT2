Saved Model : https://iiitaphyd-my.sharepoint.com/:f:/g/personal/yash_bhaskar_research_iiit_ac_in/Epof9gvucZ9HoZVa4U5oR7YBsGstnYlPqe__PpU7YLZrxA?e=bGNLUe


How to Load the Model:

1. Run the last 4 Cells of each notebook under the Heading Loading the model.
2. Use the code Under Inference for doing Inference on random Datapoints.
3. To get the metric score on the test Data, run the last cell of the Notebook.


## Fine-Tuning GPT-2 with Soft Prompts for various Task

This code provides a detailed implementation of fine-tuning the GPT-2 model with soft prompts for the task of text summarization. It employs the GPT2LMHeadModel from Hugging Face's Transformers library and a custom embedding for soft prompts to adapt the model specifically for tasks like summarization tasks.

# Features

    Soft Prompt Embedding: Incorporates a custom soft prompt, enabling the model to specialize in summarization tasks.
    Fine-Tuning on Custom Data: Utilizes a dataset for training, validation, and testing (like CNN/DailyMail dataset in this case).
    Model Customization: Enhances the base GPT-2 model with additional prompt-based embeddings.
    Comprehensive Training Loop: Includes gradient accumulation, gradient clipping, and early stopping for efficient and effective training.
    Evaluation and Testing: Provides metrics for model performance and enables testing on new text samples.

# Requirements

    Python 3.x
    PyTorch
    Transformers library
    Pandas
    Tqdm

# Usage

    Model Initialization: Create an instance of GPT2WithSoftPrompt class, which is a modified version of the GPT-2 model with an additional soft prompt embedding layer.

    Data Preparation: Load and preprocess your dataset. The script expects a CSV format with columns for articles and summaries.

    Model Training: Train the model on your dataset using the fine_tune_on_summarization function. This function takes care of the training loop, including gradient accumulation, loss calculation, and early stopping.

    Model Evaluation: After training, evaluate the model on a validation and test dataset to assess its performance.

    Model Inference: Use the trained model to generate summaries for new text inputs.

    Model Saving and Loading: The script includes functions to save and load the model, allowing you to reuse the trained model later.