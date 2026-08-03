# Refence Guide for Claude Code

This document contains the necessary information needed for Claude Code to help with the assignment efficiently.

## Important Files and Folders
1. `assignments/` - This is the folder that contains all the assignment questions. Any time a question is asked, this is the first folder you will visit to try and figure out which assignment i am talking about. Usually I'll refer the specific assignment by filename to you.

## Tech Stack
The programming language used for all kinds of code is Python. The local environment is only going to be used for generating code and verifying minor correctness and other minor issues. The actual model training will happen in Google Colab, so all code written must be in the format of jupyter notebooks.

Testing framework is pytest and for package management, uv is used.

## Coding Guidelines
1. After any new feature is added in a cell, always add pytest tests for that in the next cell. For example:

    ```python
    // New python feature
    ```

    ```python
    // Pytest tests
    ```