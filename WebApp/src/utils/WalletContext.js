// WalletContext.js
import React, { createContext, useContext, useState, useEffect, useMemo } from 'react';
import { ethers } from 'ethers'
import { CONTRACT_ADDRESS, CONTRACT_ABI } from '../utils/SmartContract';
const WalletContext = createContext();

export const WalletProvider = ({ children }) => {
    const [isConnected, setIsConnected] = useState(false);
    const [account, setAccount] = useState(null);
    const provider = new ethers.providers.Web3Provider(window.ethereum)
    const signer = provider.getSigner()

    const contract = useMemo(() => {
      return new ethers.Contract(CONTRACT_ADDRESS, CONTRACT_ABI, signer)
    }, [signer])
  
    const checkWalletConnection = async () => {
        if (window.ethereum) {
          try {
            const accounts = await window.ethereum.request({ method: 'eth_accounts' });
            if (accounts.length > 0) {
              setIsConnected(true);
              setAccount(accounts[0]);
            }
          } catch (error) {
            console.error("Error checking wallet connection:", error);
          }
        }
    };

    useEffect(() => {
      checkWalletConnection();
    }, []);

  const values = {
    account,
    contract,
    isConnected,
    checkWalletConnection,
    setIsConnected,
    setAccount,
  };

  return (
    <WalletContext.Provider value={values}>
      {children}
    </WalletContext.Provider>
  );
};

export const useWallet = () => {
  return useContext(WalletContext);
};
