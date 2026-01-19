# Changelog

All notable changes to the `kroger-mcp` package will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-05-28

### Added

- **MCP-Compatible Authentication Flow**: Implemented a new authentication flow designed for MCP environments
  - New `start_authentication` tool to begin the OAuth flow
  - New `complete_authentication` tool to finish the OAuth flow with a redirect URL
  - Better error handling and messaging for authentication issues

### Changed

- **PKCE Support**: Updated to use the Proof Key for Code Exchange (PKCE) extension for enhanced OAuth security
- **Updated Dependencies**: Now requires kroger-api >= 0.2.0 for PKCE support
- **Improved Error Messaging**: Better error messages for authentication issues

### Removed

- **Browser-Based Authentication**: Removed the automatic browser-opening authentication flow, replaced with MCP-compatible flow

### Security

- Enhanced OAuth security with PKCE support, mitigating authorization code interception attacks

## [0.1.0] - 2025-05-23

### Added

- Initial release of the Kroger MCP server
- Support for FastMCP tools to interact with the Kroger API
- Location search and management
- Product search and details
- Cart management with local tracking
- Chain and department information
- User profile and authentication
