# -*- coding: utf-8 -*-
"""weight_normalization_ae.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/13mct4TBDxXPDS5ZpJ9pH5lY3AEjfRVNT
"""

import torch 
import torchvision
import torch.nn as nn
from torch.nn.utils import weight_norm
from torch import _weight_norm
import torch.nn.functional as F
from torch.nn.parameter import Parameter, UninitializedParameter
import torch.optim as optim
from torchvision import datasets, transforms

import numpy as np
import matplotlib.pyplot as plt
from sklearn.manifold import TSNE

#this function takes in the weight attribute 'v' which is just the direction of the tensor and the magnitude
#in order to decouple the two, we must take the contiguous norm along dimension=1 of the same corresponding size input length v.
'''this is taken from the CPP implementation @ https://github.com/pytorch/pytorch/blob/517c7c98610402e2746586c78987c64c28e024aa/aten/src/ATen/native/WeightNorm.cpp#L19'''
#this must be catered to python implementation as seen below

def norm_except_dim(v, pow, dim):
    if dim == -1:
      return v.norm(pow);
    if dim != 0:
        v = v.transpose(0, dim)

    output_size = (v.size(0),) + (1,) * (v.dim() - 1)

    v = v.contiguous().view(v.size(0), -1).norm(dim=1).view(*output_size) #<- unpacks the output_size into an iterable (just one dimension)
    if dim != 0:
        v = v.transpose(0, dim)
    return v

'''This github open forum for manual implementation necessities for the WeightNorm class is very helpful. Class needs a __call__ function.
    weight_norm tries to use an instance of a class with __call__ defined (WeightNorm) as a forward pre hook. 

    OF TYPE fn = WeightNorm(name, dim)

    module.register_forward_pre_hook(fn)

    class WeightNorm:
        def __call__(...):
            ...
   https://github.com/pytorch/pytorch/issues/57289'''

def calc_weight_norm(v, g, dim):
  return torch.multiply(v, torch.multiply(g, torch.norm(v,2)))

  '''Must have explicit function declarations, similar to the forward call of a super(nn.Module) class. This includes
     class WeightNorm(), @staticmethod apply(), __call__(), remove(), weight_norm(), remove_weight_norm().'''
     #The latter two are necessities for the prehook that is called before each forward() function call in the NN class

class WeightNorm():
  def __init__(self, name="weight", dim:int = 0):
    self.name = name
    self.dim = dim

  '''Weight normalization is a reparameterization that decouples the magnitude of a weight tensor from its direction. 
     This replaces the parameter specified by name (e.g. 'weight') with two parameters: one specifying the magnitude (e.g. 'weight_g') 
     and one specifying the direction (e.g. 'weight_v'). Weight normalization is implemented via a hook that recomputes the weight tensor 
     from the magnitude and direction before every forward() call.
     
    return v*(g/at::norm_except_dim(v, 2, dim));'''

  def compute_weight(self, module: nn.Module):
    g = getattr(module, self.name + '_g')
    v = getattr(module, self.name + '_v')
    return calc_weight_norm(v, g, self.dim)
    #return _weight_norm(v, g, self.dim)
    
  @staticmethod
  def apply(module, name: str, dim: int) -> 'WeightNorm':
    for k, hook in module._forward_pre_hooks.items():
        if isinstance(hook, WeightNorm) and hook.name == name:
            raise RuntimeError("Cannot register two weight_norm hooks on the same parameter {}".format(name))
    if dim is None:
        dim = -1

    fn = WeightNorm(name, dim)

    weight = getattr(module, name)

    if isinstance(weight, UninitializedParameter):
        raise ValueError('The module passed to `WeightNorm` can\'t have uninitialized parameters. '
            'Make sure to run the dummy forward before applying weight normalization')
    # remove w from parameter list
    del module._parameters[name]

    # add g and v as new parameters and express w as g/||v|| * v
    module.register_parameter(name + '_g', Parameter(norm_except_dim(weight, 2, dim).data))
    module.register_parameter(name + '_v', Parameter(weight.data))
    setattr(module, name, fn.compute_weight(module))
    #print(f'The weight is: {weight}')
    #once we retrieve the weight value from above, we can delete the model parameter and then insert new weight_g and weight_v to the module
    setattr(module, name, fn.compute_weight(module))

    #utilize forward prehook to execute before each forward pass of the model
    #Weight normalization is implemented via a hook that recomputes the weight tensor from the magnitude and direction before every forward() call.

    module.register_forward_pre_hook(fn)
    return fn

  def remove(self, module) -> None:
    weight = self.compute_weight(module)
    delattr(module, self.name)
    del module._parameters[self.name + '_g']
    del module._parameters[self.name + '_v']
    setattr(module, self.name, Parameter(weight.data))

  def __call__(self, module, inputs):
    setattr(module, self.name, self.compute_weight(module))

#def weight_norm(module: nn.Module, name: str = 'weight', dim: int = 0) -> nn.Module:
#  WeightNorm.apply(module, name, dim)
#  return module
def remove_weight_norm(module: nn.Module, name: str = 'weight') -> nn.Module:
  for k, hook in module._forward_pre_hooks.items():
    if isinstance(hook, WeightNorm) and hook.name == name:
      hook.remove(module)
      del module._forward_pre_hooks[k]
      return module
  raise ValueError("weight_norm of '{}' not found in {}".format(name, module))

class AddGaussianNoise(object):
  ###########################   <YOUR CODE>  ############################
  def __init__(self, mu, sigma):
    self.mean = mu
    self.std = sigma
    
  def __call__(self, tensor):
    pixelNoise = torch.normal(mean=self.mean, std=self.std, size=tensor.size())
    tensor = pixelNoise + tensor
    torch.clamp(tensor, 0, 1)
    return tensor

  #########################  <END YOUR CODE>  ############################


transform_noisy = torchvision.transforms.Compose([torchvision.transforms.ToTensor(), AddGaussianNoise(0.,0.3)])
transform_original = torchvision.transforms.Compose([torchvision.transforms.ToTensor()])

train_dataset_noisy = torchvision.datasets.MNIST('data', train=True, download=True, transform=transform_noisy)
train_dataset_original = torchvision.datasets.MNIST('data', train=True, download=True, transform=transform_original)
test_dataset_noisy = torchvision.datasets.MNIST('data', train=False, download=True, transform=transform_noisy)
test_dataset_original = torchvision.datasets.MNIST('data', train=False, download=True, transform=transform_original)

print(torch.max(train_dataset_noisy.__getitem__(0)[0]).item())
print(torch.min(train_dataset_noisy.__getitem__(0)[0]).item())

class ConcatDataset(torch.utils.data.Dataset):
  def __init__(self, *datasets):
    self.datasets = datasets

  def __getitem__(self, i):
    return tuple(d[i][0] for d in self.datasets)

  def __len__(self):
    return min(len(d) for d in self.datasets)


batch_size_train, batch_size_test = 64, 1000
train_loader = torch.utils.data.DataLoader(ConcatDataset(train_dataset_noisy, train_dataset_original),
                      batch_size=batch_size_train, shuffle=True)
test_loader = torch.utils.data.DataLoader(ConcatDataset(test_dataset_noisy, test_dataset_original),
                      batch_size=batch_size_test, shuffle=False)

"""### Task 2: Create and train a denoising autoencoder
1. Build an autoencoder neural network structure with encoders and decoders that is a little more complicated than in the instructions. You can also create the network to have convolutional or transpose convolutional layers. (You can follow the instructions code skeleton with a key difference of using convolutional layers).
2. Move your model to GPU so that you can train your model with GPU. (This step can be simultaneously implemented in the above step)
3. Train your denoising autoencoder model with appropriate optimizer and **MSE** loss function. The loss function should be computed between the output of the noisy images and the clean images, i.e., $L(x, g(f(\tilde{x})))$, where $\tilde{x} = x + \epsilon$ is the noisy image and $\epsilon$ is the Gaussian niose. You should train your model with enough epochs so that your loss reaches a relatively steady value. **Note: Your loss on the test data should be lower than 20.** You may have to experiment with various model architectures to achieve this test loss.
4. Visualize your result with a 3 x 3 grid of subplots. You should show 3 test images, 3 test images with noise added, and 3 test images reconstructed after passing your noisy test images through the DAE.
"""

###########################   <YOUR CODE>  ############################
device = torch.device('cuda')

latent_feature = 16
n_latent = 64
n_channels = 1

class weight_our_AE(nn.Module):
  def __init__(self):
    super(weight_our_AE, self).__init__()

    # encoder
    self.conv1 = weight_norm(nn.Conv2d(n_channels, 32, kernel_size=2, stride=2))
    self.conv2 = nn.Conv2d(32, n_latent, kernel_size=2, stride=2)

    # decoder
    self.tran_conv2 = weight_norm(nn.ConvTranspose2d(n_latent, 16, kernel_size=2, stride=2))
    self.tran_conv1 = nn.ConvTranspose2d(16, n_channels, kernel_size=2, stride=2)

  def forward(self, x):

    # encoding layers
    x = F.relu(self.conv1(x))
    x = F.relu(self.conv2(x))

    # decoding layers
    x = F.relu(self.tran_conv2(x))
    x = torch.sigmoid(self.tran_conv1(x))
    x = x.view(-1, 1, 28, 28)
    return x

class our_AE(nn.Module):
  def __init__(self):
    super(our_AE, self).__init__()
    # encoder
    self.conv1 = nn.Conv2d(n_channels, 32, kernel_size=2, stride=2)
    self.conv2 = nn.Conv2d(32, n_latent, kernel_size=2, stride=2)

    # decoder
    self.tran_conv2 = nn.ConvTranspose2d(n_latent, 16, kernel_size=2, stride=2)
    self.tran_conv1 = nn.ConvTranspose2d(16, n_channels, kernel_size=2, stride=2)

  def forward(self, x):
    # encoding layers
    x = F.relu(self.conv1(x))
    x = F.relu(self.conv2(x))

    # decoding layers
    x = F.relu(self.tran_conv2(x))
    x = torch.sigmoid(self.tran_conv1(x))
    x = x.view(-1, 1, 28, 28)
    return x

loss_fn = nn.MSELoss(reduction='sum')
#########################  <END YOUR CODE>  ############################

def train(epoch, device, AE, optimizer):

  AE.train()

  for batch_idx, (noisy, original) in enumerate(train_loader):

    optimizer.zero_grad()
    noisy = noisy.to(device)
    original = original.to(device)
    output = AE(noisy)
    loss = loss_fn(output, original) # Here is a typical loss function (Mean square error)
    loss.backward()
    optimizer.step()

    if batch_idx % 10 == 0: # We record our output every 10 batches
      train_losses.append(loss.item()/batch_size_train) # item() is to get the value of the tensor directly
      train_counter.append(
        (batch_idx*64) + ((epoch-1)*len(train_loader.dataset)))
    if batch_idx % 100 == 0: # We visulize our output every 100 batches
      print(f'Epoch {epoch}: [{batch_idx*len(noisy)}/{len(train_loader.dataset)}] Loss: {loss.item()/batch_size_train}')


def test(epoch, device, AE):

  AE.eval() # we need to set the mode for our model

  test_loss = 0
  correct = 0

  with torch.no_grad():
    for noisy, original in test_loader:
      noisy = noisy.to(device)
      original = original.to(device)
      output = AE(noisy)
      test_loss += loss_fn(output, original).item()
  
  test_loss /= len(test_loader.dataset)
  test_counter.append(len(train_loader.dataset)*epoch)

  print(f'Test result on epoch {epoch}: Avg loss is {test_loss}')
  return test_loss

train_losses = []
train_counter = []
test_losses = []
weighted_test_loss = []
test_counter = []
epoch_list = np.linspace(1,3,3)
max_epoch = 3

AE = weight_our_AE().to(device)
optimizer = optim.Adam(AE.parameters(), lr=1e-4)
for epoch in range(1, max_epoch+1):
  train(epoch, device, AE, optimizer)
  weighted_test_loss.append(test(epoch, device, AE))

AE = our_AE().to(device)
optimizer = optim.Adam(AE.parameters(), lr=1e-4)

for epoch in range(1, max_epoch+1):
  train(epoch, device, AE, optimizer)
  test_losses.append(test(epoch, device, AE))

torch.save(AE.state_dict(),"ece570_AE_weight_norm.pth")

plt.plot(epoch_list, test_losses, label = "Non Weighted Normalization", linestyle="-", color='b')
plt.plot(epoch_list, weighted_test_loss, label = "PyTorch Implemented Weighted Normalization", linestyle="-", color='r')
plt.xlabel("Epoch")
plt.ylabel("Resulting Test Loss")
plt.legend()
plt.show()

