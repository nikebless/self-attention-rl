import sys, os, time
from datetime import datetime
import numpy as np
import matplotlib.pyplot as plt
import torch
from torch.utils.data import Dataset, DataLoader
from torch.nn.functional import one_hot
from torch.nn.utils.rnn import pad_sequence
from collections import namedtuple

sys.path.insert(-1, './ml-agents-release_10/ml-agents/mlagents/trainers')
from demo_loader import load_demonstration, get_demo_files

Step = namedtuple('Step',['observation', 'action', 'reward'])
STACK_SIZE = 6 # how many timesteps single observation includes


def parse_single_step(step, reward_zero_threshold=None, dicrete_rewards=True):
  action = step.action_info.vector_actions
  done = step.agent_info.done
  reward = step.agent_info.reward

  # zero out tiny rewards, as per discussion with Oriol
  if reward_zero_threshold is not None:
    if abs(reward) < reward_zero_threshold:
      reward = 0

  if dicrete_rewards:
    if reward > 0:
      reward = 1
    elif reward < 0:
      reward = -1 

    reward += 1 # make rewards have values of 0,1,2 instead of -1,0,1

  

  observations = []
  for sensor in step.agent_info.observations:
    stacked_observation = sensor.float_data.data

    # get only last of stacked observations
    shape = sensor.shape[0] # observations are all single-dimension vectors
    single_observation_shape = shape / STACK_SIZE
    last_step_start = int((STACK_SIZE-1)*single_observation_shape)
    last_step_observation = stacked_observation[last_step_start:]

    observations += last_step_observation

  return observations, action, reward, done


def parse_demo(info_action_pairs, reward_zero_threshold=None):
  episodes = []
  buffer = []

  for info_action in info_action_pairs:
    observation, action, reward, done = parse_single_step(info_action, reward_zero_threshold)
    buffer.append(Step(observation, action, reward))

    if done:
      episodes.append(buffer)
      buffer = []

  if len(buffer) != 0:
    episodes.append(buffer)
    buffer = []

  return episodes


def episodes_to_tensors(episodes, verbose=False, pad_val=10.):

  observations_by_episode = []
  actions_by_episode = []
  rewards_by_episode = []

  for episode in episodes:

    observations = []
    actions = []
    rewards = []

    for step in episode:
      observations.append(step.observation)
      actions.append(one_hot_encode_action(step.action, 3))
      rewards.append(step.reward)

    observations = torch.tensor(observations)
    actions = torch.stack(actions)
    rewards = torch.tensor(rewards)

    if verbose:
      print('observations:', observations.size())
      print('actions:', actions.size())
      print('rewards:', rewards.size())

    observations_by_episode.append(observations)
    actions_by_episode.append(actions)
    rewards_by_episode.append(rewards)

  observations_by_episode = pad_sequence(observations_by_episode, batch_first=True, padding_value=pad_val)
  actions_by_episode = pad_sequence(actions_by_episode, batch_first=True, padding_value=pad_val)
  rewards_by_episode = pad_sequence(rewards_by_episode, batch_first=True, padding_value=pad_val)

  if verbose:
    print('observations_by_episode:', observations_by_episode.size())
    print('actions_by_episode:', actions_by_episode.size())
    print('rewards_by_episode:', rewards_by_episode.size())
    
  return observations_by_episode, actions_by_episode, rewards_by_episode
    
def one_hot_encode_action(action, n_values=3):
  '''Encode multi-branch discrete-space action into a one-hot vector.
  
  Action is a vector of `n_values` values {0,1,2}, e.g. action=[1., 0., 2.].'''

  n_classes = n_values ** len(action)

  index = 0
  for i, value in enumerate(action):
    index += (n_values**i) * value

  index = torch.tensor(int(index))

  return one_hot(index, n_classes)


class TrajectoriesDataset(Dataset):
    def __init__(self, observations, actions, rewards):
      self.samples = []

      n_batches = observations.shape[0]

      for i_batch in range(n_batches):
        self.samples.append((observations[i_batch,:], actions[i_batch,:], rewards[i_batch,:]))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx]


if __name__ == '__main__':
  REWARD_THRESHOLD = 0.01
  PATH_TO_DEMO_DIRECTORY = './the_mayan_adventure/The Mayan Adventure Unity Project/Assets/Demonstrations/'
  # PATH_TO_DEMO = './the_mayan_adventure/The Mayan Adventure Unity Project/Assets/Demonstrations/baseline-ppo_0.demo'
  
  episodes = []

  demos_paths = get_demo_files(PATH_TO_DEMO_DIRECTORY)
  print(f'Found {len(demos_paths)} demonstration files:')
  for path_to_demo in demos_paths:
    print('- ' + path_to_demo, end=' ')
    _, info_action_pairs, _ = load_demonstration(path_to_demo)
    demo_episodes = parse_demo(info_action_pairs, REWARD_THRESHOLD)
    episodes += demo_episodes
    print(f'{len(demo_episodes)} episodes added.')

  observations, actions, rewards = episodes_to_tensors(episodes, verbose=False, pad_val=10.)

  save = True
  debug = False
  
  dataset = TrajectoriesDataset(observations, actions, rewards)

  if debug:
    loader = DataLoader(dataset, batch_size=32)

    for batch in loader:
      print(batch[2].shape)

  if save:
    dataset_name = f'./dataset-{int(time.time())}.pt'
    torch.save(dataset, dataset_name)

    print(f'Saved dataset with {len(dataset)} episodes at {dataset_name}')





