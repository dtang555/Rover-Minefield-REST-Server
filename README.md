# Rover Minefield REST Server

A FastAPI-based REST server for controlling a rover navigating a simulated minefield environment. Built for COE892 - Distributed Cloud Computing Systems at Toronto Metropolitan University.

## Overview

This project implements a client-server architecture where an operator client sends movement commands to a FastAPI server, which manages rover state and minefield logic. The server exposes REST endpoints for real-time rover control and returns state responses after each command.

## Features

- REST API built with FastAPI for rover movement and state management
- Operator client for sending real-time directional commands
- Server-side minefield grid and rover position tracking
- Request/response state handling across multiple operation scenarios

## Tech Stack

- **Language:** Python
- **Framework:** FastAPI
- **Communication:** HTTP REST

## Project Structure
