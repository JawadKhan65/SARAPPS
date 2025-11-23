import { initializeApp } from 'firebase/app';
import {
    getAuth,
    signInWithEmailAndPassword,
    signOut,
    onAuthStateChanged,
    multiFactor,
    PhoneAuthProvider,
    PhoneMultiFactorGenerator,
    RecaptchaVerifier
} from 'firebase/auth';

const firebaseConfig = {
    apiKey: "AIzaSyDjhxF8z80JlHNvDwxwe3nJHzD9vL5_Bjs",
    authDomain: "simple-todo-a93c0.firebaseapp.com",
    projectId: "simple-todo-a93c0",
    storageBucket: "simple-todo-a93c0.firebasestorage.app",
    messagingSenderId: "959228309140",
    appId: "1:959228309140:web:6ea175d878191b19738e81",
    measurementId: "G-NJ1BH18VQC"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);

export {
    auth,
    signInWithEmailAndPassword,
    signOut,
    onAuthStateChanged,
    multiFactor,
    PhoneAuthProvider,
    PhoneMultiFactorGenerator,
    RecaptchaVerifier
};

export default app;
