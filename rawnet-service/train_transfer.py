import os
import glob
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import torchaudio.transforms as T
import soundfile as sf
from model import RawNet

# 1. Configuration matching your main.py
d_args = {
    "nb_samp": 64000,
    "first_conv": 1024,
    "in_channels": 1,
    "filts": [20, [20, 20], [20, 128], [128, 128]],
    "blocks": [2, 4],
    "nb_fc_node": 1024,
    "gru_node": 1024,
    "nb_gru_layer": 3,
    "nb_classes": 2
}

# 2. Custom Dataset Loader (FFmpeg bypassed!)
class DeepfakeDataset(Dataset):
    def __init__(self, real_dir, fake_dir):
        self.filepaths = glob.glob(f"{real_dir}/*.wav") + glob.glob(f"{fake_dir}/*.wav")
        # Labels: 1 for Real, 0 for Spoof
        self.labels = [1 if "real" in path else 0 for path in self.filepaths]

    def __len__(self):
        return len(self.filepaths)

    def __getitem__(self, idx):
        path = self.filepaths[idx]
        
        # --- THE FIX: Use soundfile instead of torchaudio ---
        audio_data, sample_rate = sf.read(path)
        waveform = torch.tensor(audio_data, dtype=torch.float32)
        
        # Soundfile returns (frames,) for mono or (frames, channels) for stereo
        if waveform.ndim > 1:
            waveform = waveform.transpose(0, 1) # Convert to (channels, frames)
            waveform = torch.mean(waveform, dim=0, keepdim=True) # Force mono
        else:
            waveform = waveform.unsqueeze(0) # Force (1, frames) format
            
        # Force 16kHz
        if sample_rate != 16000:
            resampler = T.Resample(orig_freq=sample_rate, new_freq=16000)
            waveform = resampler(waveform)
            
        # Flatten back to 1D
        waveform = waveform.squeeze()

        # Pad or Truncate to exactly 64,000 samples (4 seconds)
        target_length = 64000
        current_length = waveform.shape[0]
        if current_length > target_length:
            waveform = waveform[:target_length]
        elif current_length < target_length:
            padding = target_length - current_length
            waveform = torch.nn.functional.pad(waveform, (0, padding))
            
        label = torch.tensor(self.labels[idx], dtype=torch.long)
        return waveform, label

# 3. Main Training Loop
def train():
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"🚀 Initializing Transfer Learning on {device.upper()}...")

    # Load Data
    dataset = DeepfakeDataset("training_data/real", "training_data/fake")
    dataloader = DataLoader(dataset, batch_size=16, shuffle=True)
    print(f"📁 Loaded {len(dataset)} audio files.")

    # Load Model & Weights
    model = RawNet(d_args, device).to(device)
    model.load_state_dict(torch.load("pre_trained_DF_model.pth", map_location=device, weights_only=True))
    
    # 4. FREEZE THE FRONT, UNFREEZE THE BACK
    print("❄️ Freezing feature extraction layers...")
    for name, param in model.named_parameters():
        if "gru" in name or "fc1_gru" in name or "fc2_gru" in name:
            param.requires_grad = True  # Leave brain unfrozen
        else:
            param.requires_grad = False # Freeze ears

    # Only optimize the unfrozen parameters
    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=0.0001)
    criterion = nn.NLLLoss() # Because model outputs logsoftmax

    # 5. Training Loop
    epochs = 20
    model.train()
    
    for epoch in range(epochs):
        total_loss = 0
        correct = 0
        
        for batch_idx, (waveforms, labels) in enumerate(dataloader):
            waveforms, labels = waveforms.to(device), labels.to(device)
            
            optimizer.zero_grad()
            
            # Add the batch/channel dimension [batch, 1, 64000] required by RawNet2
            outputs = model(waveforms)
            
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            
            total_loss += loss.item()
            _, predicted = torch.max(outputs.data, 1)
            correct += (predicted == labels).sum().item()
            
        accuracy = 100 * correct / len(dataset)
        print(f"Epoch [{epoch+1}/{epochs}] | Loss: {total_loss/len(dataloader):.4f} | Accuracy: {accuracy:.2f}%")

    # 6. Save the new brain
    torch.save(model.state_dict(), "fine_tuned_DF_model.pth")
    print("🎉 Training Complete! Saved new weights as 'fine_tuned_DF_model.pth'")

if __name__ == "__main__":
    train()