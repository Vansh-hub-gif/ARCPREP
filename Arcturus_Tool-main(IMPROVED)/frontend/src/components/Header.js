import React from "react";
import { Link } from "react-router-dom";
import logo from "../assets/arcturus.logo1.png";

const Header = () => {
  return (
    <header className="app-header">
      <Link to="/" className="brand-section">
        <img
          src={logo}
          alt="Arcturus Consulting Services"
          className="arcturus-logo"
        />

        <div className="header-divider"></div>

        <span className="brand-name">
          ARCPREP Intelligence Platform
        </span>
      </Link>
    </header>
  );
};

export default Header;