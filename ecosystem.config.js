module.exports = {
  apps : [
      {
        name: "litecord",
        script: "pipenv run hypercorn run:app --bind 0.0.0.0:5000",
        watch: true,
      }
  ]
}
